"""Key-field extraction (app/services/field_extraction.py) — pure, no DB.

Run with: pytest tests/test_field_extraction.py -v
"""

import re
from datetime import date

import pytest

from app.services.field_extraction import (
    STATUS_AUTO_ACCEPTED,
    STATUS_CONFIRMED,
    STATUS_NEEDS_REVIEW,
    STATUS_REJECTED,
    InvalidFieldValue,
    StoredField,
    WordSpan,
    extract_fields,
    normalise_user_value,
    render_for_model,
)

TODAY = date(2026, 10, 26)


def _typed(text, **kw):
    return extract_fields(text, text_source="text_layer", reference_date=TODAY, **kw).fields


def _words(text, low=None):
    """Word spans for every whitespace token; tokens in `low` get the
    given confidence, everything else 96."""
    low = low or {}
    return [
        WordSpan(m.start(), m.end(), low.get(m.group(0), 96.0), 1)
        for m in re.finditer(r"\S+", text)
    ]


def _ocr(text, low=None, **kw):
    return extract_fields(
        text, text_source="ocr", words=_words(text, low), document_status="ocr_extracted",
        reference_date=TODAY, **kw,
    )


def _summary(fields):
    return [(f.kind, f.role, f.value) for f in fields]


# ---- finding fields ------------------------------------------------------

def test_fir_number_and_its_registration_date():
    fields = _typed("FIRST INFORMATION REPORT (FIR) No. 214/2026 dated 12/03/2026")
    assert _summary(fields) == [("fir_number", None, "214/2026"), ("date", "fir_registered", "2026-03-12")]


def test_fir_number_is_never_misread_as_a_date():
    fields = _typed("C.R. No. 12/2026")
    assert _summary(fields) == [("fir_number", None, "12/2026")]


def test_sections_in_a_list_share_the_act():
    fields = _typed("registered under Sections 379, 411 and 34 of the Indian Penal Code")
    assert [f.value for f in fields if f.kind == "section"] == ["379 IPC", "411 IPC", "34 IPC"]


def test_section_with_letter_and_new_codes():
    fields = _typed("Bail under Section 436A CrPC, now Section 479 BNSS; offence u/s 303(2) BNS.")
    assert [f.value for f in fields] == ["436A CrPC", "479 BNSS", "303(2) BNS"]


def test_section_without_an_act_is_flagged_but_not_blocked():
    (f,) = _typed("u/s 420")
    assert f.value == "420"
    assert f.status == STATUS_AUTO_ACCEPTED
    assert [i["code"] for i in f.issues] == ["act_not_stated"]


@pytest.mark.parametrize(
    "text,role,value",
    [
        ("The accused was arrested on 14 March 2026.", "arrest", "2026-03-14"),
        ("He is in custody since 14/03/2026.", "arrest", "2026-03-14"),
        ("The next hearing is on 22 July 2026.", "hearing", "2026-07-22"),
        ("Matter adjourned to 05.08.2026 for arguments.", "hearing", "2026-08-05"),
        ("FIR registered on March 12, 2026 at 10 pm.", "fir_registered", "2026-03-12"),
        ("Order dated 1st April 2026.", "document_date", "2026-04-01"),
    ],
)
def test_english_date_formats_and_roles(text, role, value):
    (f,) = _typed(text)
    assert (f.kind, f.role, f.value) == ("date", role, value)


def test_marathi_devanagari_digits_and_verb_after_the_date():
    # "The accused was arrested on 14/03/2026" — Marathi puts the verb after.
    (f,) = _typed("आरोपीस दिनांक १४/०३/२०२६ रोजी अटक करण्यात आली.")
    assert (f.role, f.value, f.raw_text) == ("arrest", "2026-03-14", "१४/०३/२०२६")


def test_marathi_section_with_devanagari_digits():
    (f,) = _typed("कलम ३७९ भादंवि")
    assert f.value == "379 IPC"


def test_hindi_month_name():
    (f,) = _typed("अगली तारीख 22 जुलाई 2026")
    assert (f.role, f.value) == ("hearing", "2026-07-22")


# ---- checks --------------------------------------------------------------

def test_impossible_calendar_date_needs_review():
    (f,) = _typed("arrested on 31/02/2026")
    assert f.value is None and f.status == STATUS_NEEDS_REVIEW
    assert f.issues[0]["code"] == "invalid_date"


def test_arrest_in_the_future_needs_review():
    (f,) = _typed("arrested on 30 December 2026")
    assert f.status == STATUS_NEEDS_REVIEW
    assert "future_date" in [i["code"] for i in f.issues]


def test_future_hearing_is_fine():
    (f,) = _typed("next hearing on 30 December 2026")
    assert f.status == STATUS_AUTO_ACCEPTED


def test_implausible_year_needs_review():
    (f,) = _typed("arrested on 14/03/1826")
    assert "implausible_year" in [i["code"] for i in f.issues]


def test_two_digit_year_date_needs_review():
    (f,) = _typed("arrested on 14/03/26")
    assert f.value == "2026-03-14" and f.status == STATUS_NEEDS_REVIEW


def test_arrest_before_fir_registration_is_flagged():
    fields = _typed("FIR registered on 20/03/2026. The accused was arrested on 14/03/2026.")
    arrest = [f for f in fields if f.role == "arrest"][0]
    assert arrest.status == STATUS_NEEDS_REVIEW
    assert "arrest_before_fir" in [i["code"] for i in arrest.issues]


# ---- per-field confidence --------------------------------------------------

def test_field_confidence_is_its_weakest_word():
    r = _ocr("arrested on 14 March 2026.", low={"March": 58.0})
    (f,) = r.fields
    assert f.confidence == 58.0


def test_typed_text_fields_are_exact():
    (f,) = _typed("arrested on 14 March 2026.")
    assert f.confidence == 100.0 and f.status == STATUS_AUTO_ACCEPTED


def test_ocr_fields_always_need_review_by_default_even_when_confident():
    r = _ocr("FIR No. 214/2026 u/s 379 IPC arrested on 14/03/2026")
    assert {f.status for f in r.fields} == {STATUS_NEEDS_REVIEW}
    assert all(f.confidence == 96.0 for f in r.fields)


def test_ocr_auto_accept_only_when_configured_and_every_word_clears_it():
    r = _ocr(
        "u/s 379 IPC arrested on 14/03/2026",
        low={"14/03/2026": 88.0},
        auto_accept_confidence=90.0,
    )
    status = {f.kind: f.status for f in r.fields}
    assert status == {"section": STATUS_AUTO_ACCEPTED, "date": STATUS_NEEDS_REVIEW}


def test_ocr_auto_accept_never_applies_to_a_low_confidence_document():
    r = extract_fields(
        "u/s 379 IPC", text_source="ocr", words=_words("u/s 379 IPC"),
        document_status="ocr_low_confidence", reference_date=TODAY, auto_accept_confidence=50.0,
    )
    assert r.fields[0].status == STATUS_NEEDS_REVIEW


def test_low_confidence_numbers_outside_fields_are_marked_uncertain():
    text = "Seized Rs. 4500 cash and 2 phones."
    r = _ocr(text, low={"4500": 61.0, "phones.": 40.0})
    assert [text[s:e] for s, e in r.uncertain_spans] == ["4500"]  # 'phones.' has no digit


# ---- what the model sees -----------------------------------------------------

def _stored(fields):
    return [StoredField(f.kind, f.role, f.status, f.value, f.start, f.end) for f in fields]


def test_unconfirmed_fields_and_uncertain_numbers_are_masked():
    text = "FIR No. 214/2026\n\nAccused arrested on 14/03/2026 under Section 379 IPC. Seized Rs. 4500."
    r = _ocr(text, low={"4500.": 60.0})
    shown = render_for_model(text, _stored(r.fields), r.uncertain_spans)
    assert "14/03/2026" not in shown and "214/2026" not in shown and "4500" not in shown
    assert "[arrest date unclear, not yet confirmed]" in shown
    assert "Section [section unclear, not yet confirmed] IPC" in shown
    assert "[unclear number]" in shown


def test_confirmed_correction_replaces_what_ocr_read():
    text = "Accused arrested on 14/03/2026 under Section 379 IPC."
    r = _ocr(text)
    stored = _stored(r.fields)
    for s in stored:
        s.status = STATUS_CONFIRMED
    date_field = [s for s in stored if s.kind == "date"][0]
    date_field.value = "2026-03-15"  # reviewer corrected the misread day
    shown = render_for_model(text, stored, r.uncertain_spans)
    assert shown == "Accused arrested on 15 March 2026 under Section 379 IPC."


def test_rejected_field_stays_masked():
    text = "arrested on 14/03/2026"
    r = _ocr(text)
    stored = _stored(r.fields)
    stored[0].status = STATUS_REJECTED
    assert render_for_model(text, stored, []) == "arrested on [unclear]"


def test_auto_accepted_text_is_left_exactly_as_written():
    text = "Accused arrested on 14 March 2026 u/s 379 IPC."
    r = extract_fields(text, text_source="text_layer", reference_date=TODAY)
    assert render_for_model(text, _stored(r.fields), r.uncertain_spans) == text


# ---- reviewer input -----------------------------------------------------------

@pytest.mark.parametrize(
    "kind,raw,expected",
    [
        ("date", "14/03/2026", "2026-03-14"),
        ("date", "2026-03-14", "2026-03-14"),
        ("date", "१४/०३/२०२६", "2026-03-14"),
        ("section", "436a crpc", "436A CrPC"),
        ("section", "303(2) BNS", "303(2) BNS"),
        ("section", "379", "379"),
        ("fir_number", "214 / 2026", "214/2026"),
    ],
)
def test_reviewer_values_are_normalised(kind, raw, expected):
    assert normalise_user_value(kind, raw, reference_date=TODAY) == expected


@pytest.mark.parametrize(
    "kind,raw",
    [
        ("date", "31/02/2026"),
        ("date", "next tuesday"),
        ("date", "14/03/1820"),
        ("section", "Section four"),
        ("section", "379 XYZ"),
        ("fir_number", "214"),
    ],
)
def test_bad_reviewer_values_are_rejected(kind, raw):
    with pytest.raises(InvalidFieldValue):
        normalise_user_value(kind, raw, reference_date=TODAY)


# ==== form labels, role strength, priors, timeline, strict masking ========

from app.services.field_extraction import (  # noqa: E402
    ContextDate,
    ground_suggestion,
    missing_facts,
)

FIR_FORM = """FIRST INFORMATION REPORT
(Under Section 173 B.N.S.S.)
1. District: Pune City  P.S.: Swargate  Year: 2026  FIR No.: 214/2026  Date: 12/03/2026
2. Acts / Sections
   Indian Penal Code, 1860   379, 411
   Bharatiya Nyaya Sanhita, 2023   303(2)
3. (a) Occurrence of offence: Day: Monday  Date from: 09/03/2026  Date to: 09/03/2026
   (b) Information received at P.S.: Date: 12/03/2026  Time: 18:30
"""


def test_fir_form_labels_give_strong_roles():
    fields = extract_fields(FIR_FORM, text_source="text_layer", doc_type="fir", reference_date=TODAY).fields
    dates = [(f.role, f.value, f.role_basis) for f in fields if f.kind == "date"]
    assert ("offence_date", "2026-03-09", "form_label") in dates
    assert ("fir_registered", "2026-03-12", "form_label") in dates
    assert all(f.status == STATUS_AUTO_ACCEPTED for f in fields if f.kind == "date")


def test_fir_form_acts_table_rows_become_sections_without_reading_the_year():
    fields = extract_fields(FIR_FORM, text_source="text_layer", doc_type="fir", reference_date=TODAY).fields
    sections = [(f.value, f.extractor) for f in fields if f.kind == "section"]
    assert sections == [("379 IPC", "form"), ("411 IPC", "form"), ("303(2) BNS", "form")]
    assert not any(f.value and f.value.startswith(("1860", "2023")) for f in fields)


def test_marathi_form_labels():
    fields = _typed("अटक दिनांक: १४/०३/२०२६\nपुढील तारीख: २२/०७/२०२६")
    assert [(f.role, f.value, f.role_basis) for f in fields] == [
        ("arrest", "2026-03-14", "form_label"),
        ("hearing", "2026-07-22", "form_label"),
    ]


def test_far_keyword_makes_a_key_role_uncertain_even_in_typed_text():
    text = "The accused was arrested by the officers of the local crime branch unit at night on 14/03/2026"
    (f,) = _typed(text)
    assert (f.role, f.role_basis) == ("arrest", "keyword_far")
    assert f.status == STATUS_NEEDS_REVIEW
    assert "role_uncertain" in [i["code"] for i in f.issues]


def test_remand_order_latest_unexplained_date_is_a_weak_hearing():
    text = "Accused produced before the court. 14/03/2026. Remanded. 28/03/2026"
    fields = extract_fields(text, text_source="text_layer", doc_type="remand_order", reference_date=TODAY).fields
    hearing = [f for f in fields if f.role == "hearing"]
    assert [(f.value, f.role_basis, f.status) for f in hearing] == [("2026-03-28", "doc_type", STATUS_NEEDS_REVIEW)]


def test_offence_after_fir_is_flagged():
    fields = _typed("Information received at P.S. Date: 05/03/2026. The offence was committed on 09/03/2026.")
    offence = [f for f in fields if f.role == "offence_date"][0]
    assert "offence_after_fir" in [i["code"] for i in offence.issues]


def test_timeline_is_checked_against_other_documents_on_the_case():
    # Remand order says arrested 01/03; the case's FIR (another document)
    # was registered 12/03 — the new arrest date gets flagged.
    r = extract_fields(
        "The accused was arrested on 01/03/2026.", text_source="text_layer", reference_date=TODAY,
        context_dates=[ContextDate("fir_registered", date(2026, 3, 12))],
    )
    assert "arrest_before_fir" in [i["code"] for i in r.fields[0].issues]


def test_hearing_before_arrest_is_flagged():
    fields = _typed("Arrested on 14/03/2026. Next hearing on 01/03/2026.")
    hearing = [f for f in fields if f.role == "hearing"][0]
    assert "hearing_before_arrest" in [i["code"] for i in hearing.issues]


def test_strict_mode_masks_every_number_on_a_scan_outside_key_facts():
    text = "Seized Rs. 4500 cash, 2 phones, vehicle MH12AB1234 on 14/03/2026 when arrested."
    r = extract_fields(
        text, text_source="ocr", words=_words(text), document_status="ocr_extracted",
        reference_date=TODAY, mask_all_numbers=True,
    )
    shown = render_for_model(text, _stored(r.fields), r.uncertain_spans)
    for leaked in ("4500", "2 phones", "1234", "14/03/2026"):
        assert leaked not in shown
    assert shown.count("[unclear number]") == 3


def test_strict_mode_does_nothing_to_typed_text():
    text = "Seized Rs. 4500 cash."
    r = extract_fields(text, text_source="text_layer", reference_date=TODAY, mask_all_numbers=True)
    assert r.uncertain_spans == []


@pytest.mark.parametrize(
    "doc_type,present,missing",
    [
        ("fir", [("fir_number", None, "auto_accepted")], [("section", None), ("date", "fir_registered")]),
        ("fir", [("fir_number", None, "rejected"), ("section", None, "needs_review"),
                 ("date", "fir_registered", "confirmed")], [("fir_number", None)]),
        ("remand_order", [("date", "arrest", "auto_accepted")], [("date", "hearing")]),
        ("remand_order", [("date", "hearing", "needs_review")], []),
        ("unknown_type", [], []),
    ],
)
def test_missing_required_facts(doc_type, present, missing):
    assert missing_facts(doc_type, present) == missing


# ---- LLM suggestions are grounded, never trusted ---------------------------

SUGGEST_TEXT = "The accused was arrested on 14 March 2026 and produced in court under u/s 379 IPC."


def test_grounded_suggestion_becomes_a_field_needing_review():
    f = ground_suggestion(SUGGEST_TEXT, kind="date", role="arrest", quote="arrested on 14 March  2026",
                          taken=[], text_source="text_layer", reference_date=TODAY)
    assert (f.value, f.role, f.extractor, f.status) == ("2026-03-14", "arrest", "llm", STATUS_NEEDS_REVIEW)
    assert SUGGEST_TEXT[f.start:f.end] == "14 March 2026"


def test_hallucinated_quote_is_dropped():
    assert ground_suggestion(SUGGEST_TEXT, kind="date", role="arrest", quote="arrested on 15 March 2026",
                             taken=[], text_source="text_layer", reference_date=TODAY) is None


def test_quote_without_a_value_of_that_kind_is_dropped():
    assert ground_suggestion(SUGGEST_TEXT, kind="date", role="arrest", quote="produced in court",
                             taken=[], text_source="text_layer", reference_date=TODAY) is None


def test_suggestion_for_an_existing_field_is_dropped():
    s = SUGGEST_TEXT.index("379")
    assert ground_suggestion(SUGGEST_TEXT, kind="section", role=None, quote="u/s 379 IPC",
                             taken=[(s, s + 3)], text_source="text_layer", reference_date=TODAY) is None


def test_bad_role_from_the_model_is_ignored():
    f = ground_suggestion(SUGGEST_TEXT, kind="date", role="birthday", quote="14 March 2026",
                          taken=[], text_source="text_layer", reference_date=TODAY)
    assert f.role is None
