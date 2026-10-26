"""Key-field extraction with per-field confidence.

OCR gives a confidence per WORD and pdf_extraction gives one per
DOCUMENT; neither is what a case actually depends on. What matters is a
handful of facts — the FIR number, the sections cited, the offence /
FIR / arrest dates, the next hearing date — and a single misread digit in
any of them is worse than a page of misread prose. So this module:

1. finds those facts, in three passes, most reliable first:
   - "form": labels printed on the standard FIR form and court orders
     ("Information received at P.S. ... Date", "Date of arrest",
     "Next date", the Acts/Sections table, Marathi/Hindi equivalents);
   - "pattern": general patterns (English + Marathi + Hindi cues,
     Devanagari digits normalised);
   - "llm" (on demand, separately — ground_suggestion): a model's
     suggestions, accepted only if they quote the document verbatim;
2. scores each fact by its WEAKEST word (a date is only as trustworthy as
   its worst digit) and scores each date's ROLE (is it really the arrest
   date?) by how it was decided;
3. checks it: real calendar date, plausible year, no arrest/FIR/offence
   date in the future, and a consistent timeline (offence <= FIR <=
   arrest <= hearings) within the document and across the case;
4. decides whether it may be used as-is or must be confirmed by a person;
5. reports REQUIRED facts a document type should contain but doesn't, so
   a miss is visible instead of silent.

Policy (deliberately strict — see NyayMitra.md "Key fields"):
- Text-layer facts are exact text; auto-accepted unless a check fails or
  a key date's role is only weakly supported.
- OCR facts always need human confirmation unless OCR_FIELD_AUTO_ACCEPT is
  set. LLM-suggested facts always need it, full stop.
- What the chat model sees (render_for_model): unconfirmed facts masked,
  confirmed corrections applied, and on scans every other number masked
  too (strict mode), so nothing misread can reach the model as fact.

Pure functions only — no DB, no I/O — so all of it is unit-testable.
"""

from __future__ import annotations

import bisect
import calendar
import re
from dataclasses import dataclass, field
from datetime import date

# ------------------------------------------------------------- vocabulary

KIND_FIR_NUMBER = "fir_number"
KIND_SECTION = "section"
KIND_DATE = "date"
KINDS = (KIND_FIR_NUMBER, KIND_SECTION, KIND_DATE)

ROLE_ARREST = "arrest"
ROLE_FIR_REGISTERED = "fir_registered"
ROLE_HEARING = "hearing"
ROLE_OFFENCE_DATE = "offence_date"
ROLE_DOCUMENT_DATE = "document_date"
DATE_ROLES = (ROLE_ARREST, ROLE_FIR_REGISTERED, ROLE_HEARING, ROLE_OFFENCE_DATE, ROLE_DOCUMENT_DATE)
# Roles the case actually turns on — a weakly supported one needs review.
KEY_ROLES = (ROLE_ARREST, ROLE_FIR_REGISTERED, ROLE_HEARING, ROLE_OFFENCE_DATE)

STATUS_AUTO_ACCEPTED = "auto_accepted"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_CONFIRMED = "confirmed"
STATUS_REJECTED = "rejected"
STATUSES = (STATUS_AUTO_ACCEPTED, STATUS_NEEDS_REVIEW, STATUS_CONFIRMED, STATUS_REJECTED)
USABLE_STATUSES = (STATUS_AUTO_ACCEPTED, STATUS_CONFIRMED)

EXTRACTOR_FORM = "form"
EXTRACTOR_PATTERN = "pattern"
EXTRACTOR_LLM = "llm"
EXTRACTOR_MANUAL = "manual"

BASIS_FORM_LABEL = "form_label"
BASIS_KEYWORD_NEAR = "keyword_near"
BASIS_KEYWORD_FAR = "keyword_far"
BASIS_DOC_TYPE = "doc_type"
BASIS_LLM = "llm"
BASIS_REVIEWER = "reviewer"
WEAK_BASES = (BASIS_KEYWORD_FAR, BASIS_DOC_TYPE, BASIS_LLM)
_NEAR_CHARS = 30

# What each document type should contain. A missing one is reported, not
# guessed. (kind, role) — role None means "any".
REQUIRED_FACTS: dict[str, list[tuple[str, str | None]]] = {
    "fir": [(KIND_FIR_NUMBER, None), (KIND_SECTION, None), (KIND_DATE, ROLE_FIR_REGISTERED)],
    "charge_sheet": [(KIND_FIR_NUMBER, None), (KIND_SECTION, None)],
    "remand_order": [(KIND_DATE, ROLE_HEARING)],
    "bail_application": [(KIND_SECTION, None)],
    "bail_order": [(KIND_DATE, None)],
}
# What /chat tells the model is (or isn't) known for the case as a whole.
CASE_KEY_FACTS: list[tuple[str, str | None]] = [
    (KIND_FIR_NUMBER, None),
    (KIND_SECTION, None),
    (KIND_DATE, ROLE_OFFENCE_DATE),
    (KIND_DATE, ROLE_ARREST),
    (KIND_DATE, ROLE_HEARING),
]

MIN_YEAR = 1950

# ---------------------------------------------------------------- regexes

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_MONTHS = {
    # English
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    # Marathi
    "जानेवारी": 1, "फेब्रुवारी": 2, "मार्च": 3, "एप्रिल": 4, "मे": 5, "जून": 6,
    "जुलै": 7, "ऑगस्ट": 8, "सप्टेंबर": 9, "ऑक्टोबर": 10, "नोव्हेंबर": 11, "डिसेंबर": 12,
    # Hindi
    "जनवरी": 1, "फरवरी": 2, "अप्रैल": 4, "मई": 5, "जुलाई": 7, "अगस्त": 8,
    "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "नवंबर": 11, "नवम्बर": 11,
    "दिसंबर": 12, "दिसम्बर": 12,
}
_MONTH_ALT = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))

_NUMERIC_DATE_P = r"(?<!\d)(\d{1,2})\s?[./\-]\s?(\d{1,2})\s?[./\-]\s?(\d{4}|\d{2})(?!\d)"
_DMY_P = rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:day\s+of\s+)?({_MONTH_ALT})\.?,?\s*(\d{{4}})(?!\d)"
_MDY_P = rf"(?<![\w])({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})(?!\d)"
_NUMERIC_DATE = re.compile(_NUMERIC_DATE_P)
_DAY_MONTH_YEAR = re.compile(_DMY_P, re.IGNORECASE)
_MONTH_DAY_YEAR = re.compile(_MDY_P, re.IGNORECASE)
# Any date, groups stripped — for embedding in form-label rules.
_ANY_DATE_P = "(?:" + "|".join(
    re.sub(r"\((?!\?)", "(?:", p) for p in (_NUMERIC_DATE_P, _DMY_P, _MDY_P)
) + ")"
_ANY_DATE = re.compile(_ANY_DATE_P, re.IGNORECASE)

_FIR = re.compile(
    r"(?:\bF\.?\s?I\.?\s?R\.?|\bC\.?\s?R\.?|\bCrime|गु\.?\s?र\.?|गुन्हा\s+रजि(?:स्टर)?|प्राथमिकी)"
    r"\s*\)?\s*(?:No\.?|Number|नं\.?|क्र\.?|क्रमांक|संख्या)?\s*[:.\-]?\s*"
    r"(\d{1,6})\s*(?:/|of)\s*(\d{4}|\d{2})(?!\d)",
    re.IGNORECASE,
)
_FIR_NUMBER_ONLY = re.compile(r"(?<!\d)(\d{1,6})\s*(?:/|of)\s*(\d{4}|\d{2})(?!\d)", re.IGNORECASE)

_SECTION_NUM = r"\d{1,3}[A-Za-z]?(?:\s*\(\s*\d+\s*\))?"
_ACTS = [
    (r"BNSS|B\.\s?N\.\s?S\.\s?S\.?|Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita", "BNSS"),
    (r"BNS|B\.\s?N\.\s?S\.?|Bharatiya\s+Nyaya\s+Sanhita", "BNS"),
    (r"Cr\.?\s?P\.?\s?C\.?|Code\s+of\s+Criminal\s+Procedure", "CrPC"),
    (r"IPC|I\.\s?P\.\s?C\.?|Indian\s+Penal\s+Code|भा\.?\s?दं\.?\s?वि\.?|भादंवि|भारतीय\s+दंड\s+संहिता", "IPC"),
]
_ACT_ALT = "|".join(f"(?:{p})" for p, _ in _ACTS)
_LIST_SEP = r"\s*(?:,|/|&|\band\b|\bwith\b|\br/w\b|व|आणि|एवं|और)\s*"
_SECTIONS = re.compile(
    r"(?:\bunder\s+sections?|\bsections?|\bsecs?\.?|\bu/ss?\.?|कलम|धारा)\s*"
    rf"({_SECTION_NUM}(?:{_LIST_SEP}{_SECTION_NUM})*)"
    rf"(?:\s*(?:of\s+(?:the\s+)?)?({_ACT_ALT}))?",
    re.IGNORECASE,
)
_ONE_SECTION = re.compile(_SECTION_NUM)
# FIR form "Acts / Sections" table row: "Indian Penal Code, 1860   379, 411"
_ACT_TABLE_ROW = re.compile(
    rf"(?m)^[^\n]*?({_ACT_ALT})(?:\s*,?\s*(?:18|19|20)\d{{2}})?\s*[,:\-]?\s+"
    rf"({_SECTION_NUM}(?:{_LIST_SEP}{_SECTION_NUM})*)[ \t]*$",
    re.IGNORECASE,
)

_LBL_SEP = r"\s*(?:\([^)\n]{0,20}\))?\s*[:\-.]?\s*"
# Labels from the standard FIR form (CCTNS / NCRB IIF-I) and common court
# order wording. Built from the published form layout — NOT yet validated
# against real Maharashtra documents (see NyayMitra.md). `fir_only` rules
# are too generic to trust outside an FIR.
_FORM_DATE_RULES: list[tuple[re.Pattern, str, bool]] = [
    (re.compile(rf"Information\s+received\s+at\s+P\.?\s?S\.?[^\n]{{0,60}}?Date{_LBL_SEP}(?P<date>{_ANY_DATE_P})", re.I), ROLE_FIR_REGISTERED, False),
    (re.compile(rf"Date\s+(?:and|&)\s+Time\s+of\s+(?:the\s+)?F\.?I\.?R\.?{_LBL_SEP}(?P<date>{_ANY_DATE_P})", re.I), ROLE_FIR_REGISTERED, False),
    (re.compile(rf"Occurrence\s+of\s+(?:the\s+)?offen[cs]e[\s\S]{{0,150}}?Date\s+from{_LBL_SEP}(?P<date>{_ANY_DATE_P})", re.I), ROLE_OFFENCE_DATE, False),
    (re.compile(rf"\bDate\s+to{_LBL_SEP}(?P<date>{_ANY_DATE_P})", re.I), ROLE_OFFENCE_DATE, True),
    (re.compile(rf"Date\s+of\s+(?:the\s+)?(?:offen[cs]e|occurrence|incident){_LBL_SEP}(?P<date>{_ANY_DATE_P})", re.I), ROLE_OFFENCE_DATE, False),
    (re.compile(rf"Date\s+of\s+arrest{_LBL_SEP}(?P<date>{_ANY_DATE_P})", re.I), ROLE_ARREST, False),
    (re.compile(rf"Next\s+date(?:\s+of\s+hearing)?{_LBL_SEP}(?P<date>{_ANY_DATE_P})", re.I), ROLE_HEARING, False),
    (re.compile(rf"Date\s+of\s+(?:next\s+)?hearing{_LBL_SEP}(?P<date>{_ANY_DATE_P})", re.I), ROLE_HEARING, False),
    # Marathi / Hindi labels
    (re.compile(rf"अटक\s*(?:दिनांक|तारीख|दि\.){_LBL_SEP}(?P<date>{_ANY_DATE_P})"), ROLE_ARREST, False),
    (re.compile(rf"गिरफ्तारी\s*(?:की\s+)?(?:तिथि|तारीख|दिनांक){_LBL_SEP}(?P<date>{_ANY_DATE_P})"), ROLE_ARREST, False),
    (re.compile(rf"पुढील\s+(?:सुनावणी\s+)?(?:दिनांक|तारीख){_LBL_SEP}(?P<date>{_ANY_DATE_P})"), ROLE_HEARING, False),
    (re.compile(rf"अगली\s+(?:सुनवाई\s+)?(?:तिथि|तारीख){_LBL_SEP}(?P<date>{_ANY_DATE_P})"), ROLE_HEARING, False),
    (re.compile(rf"गुन्हा\s+दाखल\s+(?:दिनांक|तारीख){_LBL_SEP}(?P<date>{_ANY_DATE_P})"), ROLE_FIR_REGISTERED, False),
    (re.compile(rf"घटनेची\s+(?:दिनांक|तारीख){_LBL_SEP}(?P<date>{_ANY_DATE_P})"), ROLE_OFFENCE_DATE, False),
    (re.compile(rf"घटना\s+की\s+(?:तिथि|तारीख){_LBL_SEP}(?P<date>{_ANY_DATE_P})"), ROLE_OFFENCE_DATE, False),
]

_ROLE_KEYWORDS = {
    ROLE_ARREST: [
        "arrested", "arrest", "custody since", "taken into custody", "in custody",
        "अटक", "ताब्यात", "गिरफ्तार", "हिरासत",
    ],
    ROLE_FIR_REGISTERED: [
        "registered on", "registered", "lodged", "दाखल", "दर्ज", "पंजीकृत",
    ],
    ROLE_HEARING: [
        "next hearing", "next date", "hearing", "adjourned to", "listed on", "listed for",
        "posted to", "posted on", "सुनावणी", "पुढील तारीख", "सुनवाई", "अगली तारीख",
    ],
    ROLE_OFFENCE_DATE: [
        "offence was committed", "offence committed", "occurred on", "incident took place",
        "incident occurred", "on the night of", "घटना घडली", "घटना",
    ],
}
_FIR_HEADER_SECTIONS = {("154", "CrPC"), ("173", "BNSS")}
_DOCUMENT_DATE_KEYWORDS = ["dated", "date:", "दिनांक", "दि.", "तारीख"]
_SENTENCE_END = re.compile(r"\.\s|\n\s*\n|।")

# ------------------------------------------------------------ data types


@dataclass
class WordSpan:
    start: int
    end: int
    confidence: float
    page: int | None = None


@dataclass
class FieldCandidate:
    kind: str
    role: str | None
    raw_text: str  # exactly as it appears in the document text
    value: str | None  # normalised: ISO date, '214/2026', '379 IPC'; None if unparseable
    start: int
    end: int
    confidence: float  # 0-100: weakest word (OCR) or 100 (text layer)
    page: int | None
    extractor: str = EXTRACTOR_PATTERN
    role_basis: str | None = None
    issues: list[dict] = field(default_factory=list)
    status: str = STATUS_NEEDS_REVIEW

    def add_issue(self, code: str, message: str, *, blocking: bool) -> None:
        if not any(i["code"] == code for i in self.issues):
            self.issues.append({"code": code, "message": message, "blocking": blocking})

    @property
    def blocked(self) -> bool:
        return any(i["blocking"] for i in self.issues)


@dataclass
class FieldExtraction:
    fields: list[FieldCandidate]
    # [[start, end], ...] numbers on a scan that are masked for the model:
    # every number outside a key fact in strict mode, otherwise only those
    # below the uncertain-word confidence.
    uncertain_spans: list[list[int]]


@dataclass
class ContextDate:
    """A date fact already on the case (another document), for the
    cross-document timeline check."""

    role: str
    value: date


# ---------------------------------------------------------------- helpers


def _expand_year(raw: str) -> int:
    year = int(raw)
    if len(raw) == 2:
        current = date.today().year % 100
        year += 2000 if year <= current + 1 else 1900
    return year


def _make_date(day: int, month: int, year: int) -> str | None:
    if not 1 <= month <= 12:
        return None
    if not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    return date(year, month, day).isoformat()


def _parse_date_text(s: str) -> tuple[int, int, str] | None:
    """(day, month, year_raw) for a string that is exactly one date."""
    m = _NUMERIC_DATE.fullmatch(s)
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3)
    m = _DAY_MONTH_YEAR.fullmatch(s)
    if m:
        return int(m.group(1)), _MONTHS[m.group(2).lower()], m.group(3)
    m = _MONTH_DAY_YEAR.fullmatch(s)
    if m:
        return int(m.group(2)), _MONTHS[m.group(1).lower()], m.group(3)
    return None


def _normalise_act(raw: str | None) -> str | None:
    if not raw:
        return None
    for pattern, name in _ACTS:
        if re.fullmatch(pattern, raw.strip(), re.IGNORECASE):
            return name
    return None


def _normalise_section_number(raw: str) -> str:
    return re.sub(r"\s+", "", raw).upper()


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


class _WordIndex:
    def __init__(self, words: list[WordSpan]):
        self.words = sorted(words, key=lambda w: w.start)
        self.starts = [w.start for w in self.words]

    def covering(self, start: int, end: int) -> list[WordSpan]:
        i = max(bisect.bisect_right(self.starts, start) - 1, 0)
        out = []
        while i < len(self.words) and self.words[i].start < end:
            w = self.words[i]
            if _overlaps(w.start, w.end, start, end):
                out.append(w)
            i += 1
        return out


def _infer_date_role(text: str, start: int, end: int) -> tuple[str | None, str | None]:
    """(role, basis). Nearest role keyword in the same sentence, before OR
    after the date (Marathi/Hindi put the verb after it: "14/03/2026
    रोजी अटक"). Close = strong, far = weak."""
    before = text[max(0, start - 100):start]
    cuts = list(_SENTENCE_END.finditer(before))
    if cuts:
        before = before[cuts[-1].end():]
    after = text[end:end + 60]
    cut = _SENTENCE_END.search(after)
    if cut:
        after = after[:cut.start()]
    before_l, after_l = before.lower(), after.lower()

    best: tuple[int, str] | None = None
    for role, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            i = before_l.rfind(kw)
            if i >= 0:
                dist = len(before_l) - (i + len(kw))
                if best is None or dist < best[0]:
                    best = (dist, role)
            j = after_l.find(kw)
            if j >= 0 and (best is None or j < best[0]):
                best = (j, role)
    if best:
        return best[1], BASIS_KEYWORD_NEAR if best[0] <= _NEAR_CHARS else BASIS_KEYWORD_FAR
    if any(kw in before_l for kw in _DOCUMENT_DATE_KEYWORDS):
        return ROLE_DOCUMENT_DATE, BASIS_KEYWORD_FAR
    return None, None


def _check_date(f: FieldCandidate, year_raw: str, reference_date: date) -> None:
    if f.value is None:
        f.add_issue("invalid_date", f"'{f.raw_text}' is not a real calendar date.", blocking=True)
        return
    d = date.fromisoformat(f.value)
    if len(year_raw) == 2:
        f.add_issue("two_digit_year", f"Year written as '{year_raw}', read as {d.year}.", blocking=True)
    if not MIN_YEAR <= d.year <= reference_date.year + 1:
        f.add_issue("implausible_year", f"Year {d.year} is not plausible.", blocking=True)
    elif f.role in (ROLE_ARREST, ROLE_FIR_REGISTERED, ROLE_OFFENCE_DATE, ROLE_DOCUMENT_DATE) and d > reference_date:
        f.add_issue("future_date", "This date is after the document was uploaded.", blocking=True)


def _check_role(f: FieldCandidate) -> None:
    if f.kind != KIND_DATE:
        return
    f.issues = [i for i in f.issues if i["code"] not in ("role_unknown", "role_uncertain")]
    if f.role is None:
        f.add_issue("role_unknown", "Couldn't tell what this date is for.", blocking=False)
    elif f.role in KEY_ROLES and f.role_basis in WEAK_BASES:
        f.add_issue(
            "role_uncertain",
            f"Not sure this is the {_ROLE_LABELS[f.role]} — the wording around it is unclear.",
            blocking=True,
        )


# ------------------------------------------------------------- extraction


def extract_fields(
    text: str,
    *,
    text_source: str,
    words: list[WordSpan] | None = None,
    document_status: str | None = None,
    doc_type: str | None = None,
    reference_date: date | None = None,
    context_dates: list[ContextDate] | None = None,
    auto_accept_confidence: float | None = None,
    uncertain_word_confidence: float = 80.0,
    mask_all_numbers: bool = False,
) -> FieldExtraction:
    """text_source: 'text_layer' | 'ocr'. words: OCR word spans (offsets
    into `text`); ignored for text_layer. reference_date: the upload date.
    context_dates: date facts already on the case from other documents.
    mask_all_numbers: strict mode for scans (see module docstring)."""
    reference_date = reference_date or date.today()
    norm = text.translate(_DEVANAGARI_DIGITS)  # same length, so spans line up
    index = _WordIndex(words or []) if text_source == "ocr" else None
    fir_rules = doc_type in (None, "fir")

    fields: list[FieldCandidate] = []
    taken: list[tuple[int, int]] = []

    def free(s: int, e: int) -> bool:
        return not any(_overlaps(s, e, a, b) for a, b in taken)

    def score(s: int, e: int) -> tuple[float, int | None]:
        if index is None:
            return 100.0, None
        covering = index.covering(s, e)
        if not covering:
            return 0.0, None
        return min(w.confidence for w in covering), covering[0].page

    def add_date(s: int, e: int, role: str | None, basis: str | None, extractor: str) -> None:
        parsed = _parse_date_text(norm[s:e])
        if parsed is None:
            return
        day, month, year_raw = parsed
        conf, page = score(s, e)
        f = FieldCandidate(
            KIND_DATE, role, text[s:e], _make_date(day, month, _expand_year(year_raw)),
            s, e, conf, page, extractor=extractor, role_basis=basis,
        )
        _check_date(f, year_raw, reference_date)
        fields.append(f)
        taken.append((s, e))

    def add_sections(list_text_start: int, list_text: str, act_raw: str | None, extractor: str) -> None:
        act = _normalise_act(act_raw)
        for n in _ONE_SECTION.finditer(list_text):
            s, e = list_text_start + n.start(), list_text_start + n.end()
            if not free(s, e):
                continue
            number = _normalise_section_number(n.group(0))
            if fir_rules and s < 200 and (number, act) in _FIR_HEADER_SECTIONS:
                # "FIRST INFORMATION REPORT (Under Section 154 Cr.P.C.)" —
                # the procedure the form is filed under, not an offence.
                taken.append((s, e))
                continue
            conf, page = score(s, e)
            f = FieldCandidate(
                KIND_SECTION, None, text[s:e], f"{number} {act}" if act else number, s, e, conf, page,
                extractor=extractor,
            )
            if act is None:
                f.add_issue("act_not_stated", "The Act (IPC/CrPC/BNS/BNSS) isn't stated next to it.", blocking=False)
            fields.append(f)
            taken.append((s, e))

    # 1. FIR numbers — first, so "FIR No. 214/2026" is never read as a date.
    for m in _FIR.finditer(norm):
        s, e = m.start(), m.end()
        number, year_raw = m.group(1), m.group(2)
        conf, page = score(m.start(1), m.end(2))
        year = _expand_year(year_raw)
        f = FieldCandidate(
            KIND_FIR_NUMBER, None, text[s:e], f"{int(number)}/{year}", s, e, conf, page,
            extractor=EXTRACTOR_FORM if fir_rules else EXTRACTOR_PATTERN,
        )
        if len(year_raw) == 2:
            f.add_issue("two_digit_year", f"Year written as '{year_raw}', read as {year}.", blocking=False)
        if not MIN_YEAR <= year <= reference_date.year + 1:
            f.add_issue("implausible_year", f"Year {year} is not plausible for an FIR.", blocking=True)
        fields.append(f)
        taken.append((s, e))

    # 2. Form labels (strongest role evidence).
    for rule, role, fir_only in _FORM_DATE_RULES:
        if fir_only and not fir_rules:
            continue
        for m in rule.finditer(norm):
            s, e = m.span("date")
            if free(s, e):
                add_date(s, e, role, BASIS_FORM_LABEL, EXTRACTOR_FORM)
    for m in _ACT_TABLE_ROW.finditer(norm):
        add_sections(m.start(2), m.group(2), m.group(1), EXTRACTOR_FORM)

    # 3. General patterns.
    for m in _SECTIONS.finditer(norm):
        add_sections(m.start(1), m.group(1), m.group(2), EXTRACTOR_PATTERN)

    date_spans: list[tuple[int, int]] = []
    for rx in (_NUMERIC_DATE, _DAY_MONTH_YEAR, _MONTH_DAY_YEAR):
        date_spans.extend(m.span() for m in rx.finditer(norm))
    for s, e in sorted(date_spans):
        if not free(s, e):
            continue
        role, basis = _infer_date_role(norm, s, e)
        # "FIR No. 214/2026 dated 14/03/2026" — a date right after an FIR
        # number is the FIR's registration date.
        if role in (None, ROLE_DOCUMENT_DATE) and any(
            f.kind == KIND_FIR_NUMBER and 0 <= s - f.end <= 25 for f in fields
        ):
            role, basis = ROLE_FIR_REGISTERED, BASIS_KEYWORD_NEAR
        add_date(s, e, role, basis, EXTRACTOR_PATTERN)

    # 4. Document-type priors for dates nothing else explained.
    if doc_type == "remand_order":
        # A remand order's latest date with no other role is almost always
        # the next date — weak evidence, so it goes to review.
        unexplained = [f for f in fields if f.kind == KIND_DATE and f.role is None and f.value]
        if unexplained and not any(f.role == ROLE_HEARING for f in fields):
            latest = max(unexplained, key=lambda f: f.value)
            latest.role, latest.role_basis = ROLE_HEARING, BASIS_DOC_TYPE

    for f in fields:
        if f.kind == KIND_DATE and f.value:
            # role may have changed since _check_date ran
            if f.role in (ROLE_ARREST, ROLE_FIR_REGISTERED, ROLE_OFFENCE_DATE, ROLE_DOCUMENT_DATE) \
                    and date.fromisoformat(f.value) > reference_date:
                f.add_issue("future_date", "This date is after the document was uploaded.", blocking=True)
        _check_role(f)

    check_timeline(fields, context_dates or [])

    for f in fields:
        f.status = decide_status(
            f, text_source=text_source, document_status=document_status,
            auto_accept_confidence=auto_accept_confidence,
        )

    fields.sort(key=lambda f: f.start)
    masked = _masked_number_spans(norm, index, taken, uncertain_word_confidence, mask_all_numbers)
    return FieldExtraction(fields=fields, uncertain_spans=masked)


def decide_status(
    f: FieldCandidate, *, text_source: str, document_status: str | None,
    auto_accept_confidence: float | None,
) -> str:
    if f.blocked or f.extractor == EXTRACTOR_LLM:
        return STATUS_NEEDS_REVIEW
    if text_source == "text_layer":
        return STATUS_AUTO_ACCEPTED
    if (
        text_source == "ocr"
        and auto_accept_confidence is not None
        and document_status == "ocr_extracted"
        and f.confidence >= auto_accept_confidence
    ):
        return STATUS_AUTO_ACCEPTED
    return STATUS_NEEDS_REVIEW


def check_timeline(fields: list[FieldCandidate], context_dates: list[ContextDate]) -> None:
    """offence <= FIR registration <= arrest <= hearings, within this
    document AND against dates already on the case. Only the new fields
    are flagged — existing ones may already be confirmed."""
    known: dict[str, list[date]] = {}
    for c in context_dates:
        known.setdefault(c.role, []).append(c.value)
    for f in fields:
        if f.kind == KIND_DATE and f.value and f.role:
            known.setdefault(f.role, []).append(date.fromisoformat(f.value))

    def earliest(role: str) -> date | None:
        return min(known[role]) if known.get(role) else None

    def latest(role: str) -> date | None:
        return max(known[role]) if known.get(role) else None

    for f in fields:
        if f.kind != KIND_DATE or not f.value or not f.role:
            continue
        d = date.fromisoformat(f.value)
        fir, offence_latest, arrest_earliest = earliest(ROLE_FIR_REGISTERED), latest(ROLE_OFFENCE_DATE), earliest(ROLE_ARREST)
        if f.role == ROLE_ARREST:
            if fir and d < fir:
                f.add_issue("arrest_before_fir", "Arrest date is before the FIR registration date — check both.", blocking=True)
            if offence_latest and d < offence_latest:
                f.add_issue("arrest_before_offence", "Arrest date is before the offence date — check both.", blocking=True)
        elif f.role == ROLE_OFFENCE_DATE:
            if fir and d > fir:
                f.add_issue("offence_after_fir", "Offence date is after the FIR was registered — check both.", blocking=True)
        elif f.role == ROLE_FIR_REGISTERED:
            if offence_latest and d < offence_latest:
                f.add_issue("offence_after_fir", "FIR registration is before the offence date — check both.", blocking=True)
            if arrest_earliest and d > arrest_earliest:
                f.add_issue("arrest_before_fir", "FIR registration is after the arrest date — check both.", blocking=True)
        elif f.role == ROLE_HEARING:
            if arrest_earliest and d < arrest_earliest:
                f.add_issue("hearing_before_arrest", "Hearing date is before the arrest date — check both.", blocking=True)


def _masked_number_spans(
    norm: str, index: _WordIndex | None, taken: list[tuple[int, int]],
    threshold: float, mask_all: bool,
) -> list[list[int]]:
    if index is None:
        return []
    spans: list[list[int]] = []
    for w in index.words:
        if not mask_all and w.confidence >= threshold:
            continue
        if not any(ch.isdigit() for ch in norm[w.start:w.end]):
            continue
        if any(_overlaps(w.start, w.end, a, b) for a, b in taken):
            continue
        if spans and w.start - spans[-1][1] <= 1:
            spans[-1][1] = w.end
        else:
            spans.append([w.start, w.end])
    return spans


def missing_facts(doc_type: str, present: list[tuple[str, str | None, str]]) -> list[tuple[str, str | None]]:
    """Required (kind, role) facts for this document type with no
    non-rejected field. present: (kind, role, status) of the document's
    fields."""
    out = []
    for kind, role in REQUIRED_FACTS.get(doc_type, []):
        found = any(
            k == kind and (role is None or r == role) and st != STATUS_REJECTED for k, r, st in present
        )
        if not found:
            out.append((kind, role))
    return out


# ---------------------------------------------------- LLM suggestions


def ground_suggestion(
    text: str,
    *,
    kind: str,
    role: str | None,
    quote: str,
    taken: list[tuple[int, int]],
    text_source: str,
    reference_date: date | None = None,
) -> FieldCandidate | None:
    """Turns a model's suggestion into a field ONLY if its quote is in the
    document verbatim (whitespace-tolerant) and actually contains a value
    of that kind; otherwise None. The model is never trusted for the value
    itself — the value is parsed from the document text at the quoted
    spot, exactly like any other field, and always needs review."""
    reference_date = reference_date or date.today()
    if kind not in KINDS or not isinstance(quote, str) or not quote.strip():
        return None
    norm = text.translate(_DEVANAGARI_DIGITS)
    pattern = r"\s+".join(re.escape(tok) for tok in quote.translate(_DEVANAGARI_DIGITS).split())
    for qm in re.finditer(pattern, norm):
        q_start, q_text = qm.start(), qm.group(0)
        if kind == KIND_DATE:
            m = _ANY_DATE.search(q_text)
            if not m:
                return None
            s, e = q_start + m.start(), q_start + m.end()
        elif kind == KIND_SECTION:
            m = _ONE_SECTION.search(q_text)
            if not m:
                return None
            s, e = q_start + m.start(), q_start + m.end()
        else:
            m = _FIR_NUMBER_ONLY.search(q_text)
            if not m:
                return None
            s, e = q_start + m.start(), q_start + m.end()
        if any(_overlaps(s, e, a, b) for a, b in taken):
            continue  # already a field — try the next occurrence
        conf = 100.0 if text_source == "text_layer" else 0.0
        if kind == KIND_DATE:
            parsed = _parse_date_text(norm[s:e])
            if parsed is None:
                return None
            day, month, year_raw = parsed
            f = FieldCandidate(
                KIND_DATE, role if role in DATE_ROLES else None, text[s:e],
                _make_date(day, month, _expand_year(year_raw)), s, e, conf, None,
                extractor=EXTRACTOR_LLM, role_basis=BASIS_LLM if role in DATE_ROLES else None,
            )
            _check_date(f, year_raw, reference_date)
            _check_role(f)
        elif kind == KIND_SECTION:
            act = _normalise_act(m2.group(0)) if (m2 := re.search(_ACT_ALT, q_text, re.I)) else None
            number = _normalise_section_number(norm[s:e])
            f = FieldCandidate(
                KIND_SECTION, None, text[s:e], f"{number} {act}" if act else number, s, e, conf, None,
                extractor=EXTRACTOR_LLM,
            )
        else:
            fm = _FIR_NUMBER_ONLY.fullmatch(norm[s:e])
            year = _expand_year(fm.group(2))
            f = FieldCandidate(
                KIND_FIR_NUMBER, None, text[s:e], f"{int(fm.group(1))}/{year}", s, e, conf, None,
                extractor=EXTRACTOR_LLM,
            )
        if text_source != "text_layer":
            f.add_issue("scan_confidence_unknown", "Found by AI in a scan; how clearly it was read is unknown.", blocking=False)
        f.add_issue("found_by_ai", "Suggested by the AI — check it against the original.", blocking=True)
        f.status = STATUS_NEEDS_REVIEW
        return f
    return None


# ----------------------------------------------- human corrections (API)


class InvalidFieldValue(ValueError):
    pass


def normalise_user_value(kind: str, raw: str, *, reference_date: date | None = None) -> str:
    """Validates a value a reviewer typed in. Raises InvalidFieldValue."""
    reference_date = reference_date or date.today()
    raw = raw.strip().translate(_DEVANAGARI_DIGITS)
    if kind == KIND_DATE:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = re.fullmatch(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})", raw)
            if not m:
                raise InvalidFieldValue("Enter the date as DD/MM/YYYY.")
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        value = _make_date(d, mo, y)
        if value is None:
            raise InvalidFieldValue("That is not a real calendar date.")
        if not MIN_YEAR <= y <= reference_date.year + 5:
            raise InvalidFieldValue("That year is not plausible.")
        return value
    if kind == KIND_SECTION:
        m = re.fullmatch(rf"({_SECTION_NUM})(?:\s+({_ACT_ALT}))?", raw, re.IGNORECASE)
        if not m:
            raise InvalidFieldValue("Enter a section like '436A CrPC' or '379 IPC'.")
        number = _normalise_section_number(m.group(1))
        act = _normalise_act(m.group(2))
        if m.group(2) and act is None:
            raise InvalidFieldValue("Act must be IPC, CrPC, BNS or BNSS.")
        return f"{number} {act}" if act else number
    if kind == KIND_FIR_NUMBER:
        m = re.fullmatch(r"(\d{1,6})\s*/\s*(\d{4})", raw)
        if not m:
            raise InvalidFieldValue("Enter the FIR number as NUMBER/YEAR, e.g. 214/2026.")
        year = int(m.group(2))
        if not MIN_YEAR <= year <= reference_date.year + 1:
            raise InvalidFieldValue("That year is not plausible.")
        return f"{int(m.group(1))}/{year}"
    raise InvalidFieldValue(f"Unknown field kind {kind!r}.")


# ------------------------------------------------- what the model may see

_ROLE_LABELS = {
    ROLE_ARREST: "arrest date",
    ROLE_FIR_REGISTERED: "FIR registration date",
    ROLE_HEARING: "hearing date",
    ROLE_OFFENCE_DATE: "offence date",
    ROLE_DOCUMENT_DATE: "document date",
}


def field_label(kind: str, role: str | None) -> str:
    if kind == KIND_DATE:
        return _ROLE_LABELS.get(role, "date")
    return {KIND_SECTION: "section", KIND_FIR_NUMBER: "FIR number"}[kind]


def display_value(kind: str, value: str | None) -> str:
    if value is None:
        return "unclear"
    if kind == KIND_DATE:
        d = date.fromisoformat(value)
        return f"{d.day} {calendar.month_name[d.month]} {d.year}"
    if kind == KIND_SECTION:
        return f"Section {value}"
    return f"FIR No. {value}"


def inline_value(kind: str, value: str | None) -> str:
    """Replacement text for a confirmed field inside the document text.
    A section's span covers only its number ("Section 379 IPC" -> "379"),
    so only the number goes back in; dates and FIR numbers span the whole
    expression and get the full display form."""
    if kind == KIND_SECTION and value:
        return value.split(" ")[0]
    return display_value(kind, value)


@dataclass
class StoredField:
    """The subset of a document_fields row render_for_model needs."""

    kind: str
    role: str | None
    status: str
    value: str | None
    span_start: int | None
    span_end: int | None


def render_for_model(text: str, fields: list[StoredField], uncertain_spans: list[list[int]]) -> str:
    """The document text as the chat model may see it:
    - auto_accepted: left exactly as written;
    - confirmed: replaced by the confirmed value (a reviewer's correction
      wins over what OCR read);
    - needs_review / rejected: masked, so an unconfirmed date or section is
      never presented to the model as fact;
    - masked numbers (see FieldExtraction.uncertain_spans): masked.
    Hand-added facts have no span and aren't in the text at all.
    """
    replacements: list[tuple[int, int, str]] = []
    for f in fields:
        if f.span_start is None or f.span_end is None:
            continue
        if f.status == STATUS_AUTO_ACCEPTED:
            replacements.append((f.span_start, f.span_end, text[f.span_start:f.span_end]))
        elif f.status == STATUS_CONFIRMED:
            replacements.append((f.span_start, f.span_end, inline_value(f.kind, f.value)))
        elif f.status == STATUS_NEEDS_REVIEW:
            replacements.append(
                (f.span_start, f.span_end, f"[{field_label(f.kind, f.role)} unclear, not yet confirmed]")
            )
        else:  # rejected
            replacements.append((f.span_start, f.span_end, "[unclear]"))
    for s, e in uncertain_spans:
        replacements.append((s, e, "[unclear number]"))

    replacements.sort(key=lambda r: r[0])
    out: list[str] = []
    cursor = 0
    for s, e, rep in replacements:
        if s < cursor or e > len(text):
            continue  # overlapping/out-of-range span: keep the first, skip the rest
        out.append(text[cursor:s])
        out.append(rep)
        cursor = e
    out.append(text[cursor:])
    return "".join(out)
