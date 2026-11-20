"""A small, hand-written reference of the procedural rights that matter
most to an undertrial's family, given to the model as RELEVANT LAW.

Why it exists: without any law text the model answers law questions from
memory, and nyaymitra-v2 got Section 436A CrPC wrong when tested that way
(demo/.state/compare.json). Grounding the answer in a short, checked
summary fixes that for the questions families ask most.

What it is NOT: the bare Act text, or a complete retrieval system. Each
entry is a plain-language summary of the CrPC 1973 section and the BNSS
2023 section that replaced it (BNSS applies to cases registered from
1 July 2024). Every entry must be checked against the official text by
the project guide or a lawyer before public use; KB_REVIEWED_BY records
who did that. Retrieval is keyword matching on the question, which keeps
the behaviour predictable and testable.
"""

import re
from dataclasses import dataclass

KB_VERSION = "2026-11-20"
KB_REVIEWED_BY = ""  # fill in name + date once a lawyer/guide has checked every entry


@dataclass(frozen=True)
class Provision:
    key: str
    title: str
    summary: str
    patterns: tuple[str, ...]  # regexes matched against the lower-cased question


PROVISIONS: tuple[Provision, ...] = (
    Provision(
        key="max_undertrial_detention",
        title="Section 436A CrPC / Section 479 BNSS — maximum time an undertrial can be kept in jail",
        summary=(
            "If an undertrial has spent up to half of the maximum jail term for the offence, "
            "the court shall release them on a personal bond, with or without sureties. "
            "Under Section 436A CrPC this does not cover offences punishable with death. "
            "Under Section 479 BNSS it also does not cover offences punishable with life imprisonment. "
            "Under Section 479 BNSS a first-time offender (never convicted before) is to be released "
            "after one-third of the maximum term. The court can order longer detention only after hearing "
            "the Public Prosecutor and giving written reasons. Time lost because of delay caused by the accused "
            "is not counted. No undertrial can be kept in jail longer than the maximum sentence for the offence. "
            "Under BNSS the jail superintendent must apply to the court once the period is completed."
        ),
        patterns=(r"436\s*-?\s*a", r"\b479\b", r"undertrial", r"under-trial", r"how long.*(jail|prison|inside|without (a )?(verdict|trial|judgment))",
                  r"(half|one.third).*(sentence|punishment)", r"personal bond", r"(kept|keep|stay).*(jail|prison)"),
    ),
    Provision(
        key="default_bail",
        title="Section 167(2) CrPC / Section 187 BNSS — time limit for the charge sheet (default bail)",
        summary=(
            "Police custody can be at most 15 days in total; after that the person is in judicial custody (jail). "
            "If the police do not file the charge sheet within 90 days (offences punishable with death, life "
            "imprisonment or at least 10 years) or 60 days (all other offences), the accused gets a right to bail, "
            "called default bail, if they apply for it and are ready to give bail. The right must be claimed "
            "before the charge sheet is filed."
        ),
        patterns=(r"charge.?sheet", r"chargesheet", r"\b167\b", r"\b187\b", r"default bail", r"60 days", r"90 days",
                  r"police custody", r"judicial custody", r"remand"),
    ),
    Provision(
        key="production_24h",
        title="Section 57 CrPC / Section 58 BNSS and Article 22(2) of the Constitution — 24 hours to reach a magistrate",
        summary=(
            "A person arrested without a warrant must be produced before the nearest magistrate within 24 hours, "
            "not counting travel time. Police cannot keep them longer without the magistrate's order."
        ),
        patterns=(r"24 hours", r"twenty.four hours", r"\b57\b", r"\b58\b", r"magistrate", r"produce", r"article 22"),
    ),
    Provision(
        key="grounds_of_arrest",
        title="Section 50 CrPC / Section 47 BNSS — right to know why they were arrested",
        summary=(
            "Police must tell the arrested person the full reasons (grounds) for the arrest. If the offence is "
            "bailable, police must also tell them they have a right to bail. Under Section 50A CrPC / Section 48 BNSS "
            "police must inform a relative or friend about the arrest and where the person is held."
        ),
        # Not "why was he arrested?" — that asks about the case's facts, and
        # with this rule in view the model claimed police broke it.
        patterns=(r"grounds? of arrest", r"right to know", r"(police|they) (did not|didn't|never) (tell|inform)",
                  r"\b50a?\b", r"\b47\b", r"\b48\b", r"(inform|tell).*(family|relative)"),
    ),
    Provision(
        key="bailable_bail",
        title="Section 436 CrPC / Section 478 BNSS — bail in bailable offences",
        summary=(
            "For a bailable offence, bail is a right: the police or the court must release the person once they give "
            "bail (with or without sureties). A poor person who cannot arrange sureties can be released on a personal bond."
        ),
        patterns=(r"bailable", r"\bbail\b", r"\b436\b(?!\s*-?\s*a)", r"\b478\b", r"surety", r"sureties"),
    ),
    Provision(
        key="non_bailable_bail",
        title="Sections 437 and 439 CrPC / Sections 480 and 483 BNSS — bail in non-bailable offences",
        summary=(
            "For a non-bailable offence, bail is not automatic; the court decides. A magistrate can grant bail under "
            "Section 437 CrPC / 480 BNSS, and the Sessions Court or High Court under Section 439 CrPC / 483 BNSS. "
            "The court looks at things like how serious the offence is, the evidence, and whether the person might "
            "run away or influence witnesses. The family's lawyer files the bail application."
        ),
        patterns=(r"\bbail\b", r"non.bailable", r"\b437\b", r"\b439\b", r"\b480\b", r"\b483\b", r"get out", r"release"),
    ),
    Provision(
        key="legal_aid",
        title="Article 39A of the Constitution, Section 12 Legal Services Authorities Act 1987, Section 304 CrPC / Section 341 BNSS — free lawyer",
        summary=(
            "A person in custody is entitled to free legal services. The family can ask the District Legal Services "
            "Authority (DLSA) at the district court, or the court itself, for a free lawyer. In a trial, if the accused "
            "cannot afford a lawyer, the court must give one at the State's cost."
        ),
        patterns=(r"legal aid", r"free (lawyer|advocate|legal)", r"afford", r"no (lawyer|advocate)", r"\bdlsa\b",
                  r"\b304\b", r"\b341\b", r"39a", r"(need|get|find).*(lawyer|advocate)"),
    ),
    Provision(
        key="meet_lawyer",
        title="Section 41D CrPC / Section 38 BNSS — right to meet a lawyer",
        summary=(
            "An arrested person may meet a lawyer of their choice during interrogation, though not for the whole of it."
        ),
        patterns=(r"\b41d\b", r"\b38\b", r"meet.*(lawyer|advocate)", r"talk to.*(lawyer|advocate)", r"interrogat"),
    ),
)

_BY_KEY = {p.key: p for p in PROVISIONS}

# Said before the summaries so the model does not read a duty ("police
# must tell...") as a statement about what happened in this case.
LAW_HEADER = (
    "General rules of law. They apply to everyone and do not say what happened in this case. "
    "Use them only to explain the law; never claim the police or the court did or did not follow them."
)


def find_provisions(question: str, limit: int = 2) -> list[Provision]:
    """Provisions whose patterns match the question, most matches first
    (ties keep the order above). Empty when nothing matches — the caller
    then sends no law text rather than an unrelated one."""
    q = re.sub(r"\s+", " ", question.lower())
    scored = []
    for order, p in enumerate(PROVISIONS):
        hits = sum(1 for pat in p.patterns if re.search(pat, q))
        if hits:
            scored.append((-hits, order, p))
    scored.sort()
    return [p for _, _, p in scored[:limit]]


def statute_context(question: str, limit: int = 2) -> str:
    """RELEVANT LAW block for the prompt ("" when nothing matches)."""
    found = find_provisions(question, limit)
    if not found:
        return ""
    return LAW_HEADER + "\n\n" + "\n\n".join(f"{p.title}:\n{p.summary}" for p in found)
