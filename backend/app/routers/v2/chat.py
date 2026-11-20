import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...config import settings
from ...db.models import Case, Hearing
from ...dependencies import CurrentUser, require_case_member_from_body
from ...llm.base import LLMProvider, LLMUnavailable
from ...llm.factory import get_llm
from ...models.v2.chat import ChatRequest, ChatResponse, CitedDocument, SkippedDocument
from ...services.v2.case_document_context import (
    fetch_case_document_context,
    fetch_excluded_documents,
)
from ...services.v2.chat_generation import generate_draft
from ...services.v2.document_fields import case_facts
from ...services.v2.verification import verify_draft

router = APIRouter()

# Dates are stored in UTC; families read them as Indian dates (a hearing
# on 26 Nov is 25 Nov 18:30 UTC). India has no daylight saving, so a
# fixed offset is exact.
_LOCAL_TZ = timezone(timedelta(minutes=settings.display_utc_offset_minutes))


def _day(dt: datetime) -> str:
    return dt.astimezone(_LOCAL_TZ).strftime("%d %B %Y").lstrip("0")


def _describe_hearing(h: Hearing) -> str:
    parts = [_day(h.date)]
    if h.court:
        parts.append(h.court)
    if h.purpose:
        parts.append(h.purpose)
    text = ", ".join(parts)
    return text if h.status == "scheduled" else f"{text} ({h.status})"


def hearing_details(db: Session, case_id: uuid.UUID) -> dict:
    """The hearing schedule the advocate keeps in the app. It is newer than
    any hearing date printed in an uploaded document (an FIR's "next
    hearing" is long out of date by the time the family asks)."""
    hearings = db.scalars(
        select(Hearing).where(Hearing.case_id == case_id).order_by(Hearing.date.asc())
    ).all()
    now = datetime.now(timezone.utc)
    upcoming = [h for h in hearings if h.status in ("scheduled", "adjourned") and h.date >= now - timedelta(hours=12)]
    past = [h for h in hearings if h not in upcoming]
    out: dict = {}
    if upcoming:
        out["nextHearing"] = _describe_hearing(upcoming[0])
        if len(upcoming) > 1:
            out["laterHearings"] = [_describe_hearing(h) for h in upcoming[1:4]]
    if past:
        out["pastHearings"] = [_describe_hearing(h) for h in past[-3:]]
    if out:
        out["hearingNote"] = (
            "These hearing dates are from the advocate's case record and are the most up to date. "
            "A hearing date printed in an older document may have changed."
        )
    return out

# A bare greeting gets an instant, fixed reply instead of a ~40 s model
# call that (seen live) answers "hi" by dumping the case documents back.
_GREETING = re.compile(
    r"^\s*(hi+|hello+|helo|hey+|hii+|yo|namaste|namaskar|namaskaar|"
    r"good\s+(morning|afternoon|evening)|नमस्ते|नमस्कार)[\s!.?,]*$",
    re.IGNORECASE,
)
GREETING_REPLY = (
    "Namaste! I can explain your case documents in simple words — for "
    "example what the FIR says, which sections apply, or when the next "
    "hearing is. What would you like to know?"
)

# caseId is optional on this endpoint (the chatbot FAB is portal-home-level
# for Advocate/NGO, with no single case in scope there) — the membership
# check only applies when a caseId is actually present.
_require_optional_case_member = require_case_member_from_body("caseId", optional=True)

# OCR: scanned PDFs are read at upload time (app/services/pdf_extraction.py,
#     app/services/ocr/). A scan below OCR_MIN_CONFIDENCE is stored but kept
#     out of the context below and reported in skippedDocuments instead.
# TODO(ner_service): no jurisdiction/statute extraction yet — CASE
#     DETAILS in the prompt comes from the case's own Postgres columns,
#     not NER over its documents.
# TODO(retrieval_service): no case-law retrieval yet — that's a
#     cross-encoder reranker over past judgments, separate from the
#     case's own documents fetched below.
# TODO(translation_service): no Bhashini translation yet — replies are
#     English-only regardless of the caller's preferred language.


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: CurrentUser = Depends(_require_optional_case_member),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm),
) -> ChatResponse:
    if _GREETING.match(payload.message):
        # Not a model answer, so nothing to verify — and never "verified".
        return ChatResponse(text=GREETING_REPLY, verificationStatus="unverified", modelUsed="greeting", latencyMs=0)
    case_details: dict = {}
    cited_documents: list[CitedDocument] = []
    skipped_documents: list[SkippedDocument] = []
    documents = []
    pending_review = 0

    if payload.caseId:
        case_id = uuid.UUID(payload.caseId)
        # The dependency above already confirmed current_user is a member
        # of this case — a CaseMember row can't exist without a valid
        # case_id (FK), so this is never None in practice, but a 404 here
        # beats a 500 if that ever stopped being true.
        case = db.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        case_details = {
            "undertrialName": case.undertrial_name,
            "firNumber": case.fir_number,
            "court": case.court,
            "stage": case.stage,
        }
        case_details.update(hearing_details(db, case_id))

        documents, _truncated = fetch_case_document_context(db, case_id)
        cited_documents = [
            CitedDocument(
                docId=d.doc_id,
                docType=d.doc_type,
                textSource=d.text_source,
                ocrConfidence=d.ocr_confidence,
            )
            for d in documents
        ]
        skipped_documents = [
            SkippedDocument(
                docId=d.doc_id,
                docType=d.doc_type,
                reason=d.reason,
                ocrConfidence=d.ocr_confidence,
            )
            for d in fetch_excluded_documents(db, case_id)
        ]
        # Only facts that are exact text or confirmed by a person; the
        # model is told the basis of each. Unconfirmed ones are masked in
        # the document text (case_document_context.py) and only counted here.
        facts = case_facts(db, case_id)
        pending_review = facts.pending_review
        if facts.facts:
            case_details["confirmedFactsFromDocuments"] = facts.facts
        if facts.not_found:
            case_details["notFoundInDocuments"] = (
                ", ".join(facts.not_found)
                + " — not found in the uploaded documents. Do not guess these."
            )
        if pending_review:
            case_details["factsAwaitingConfirmation"] = (
                f"{pending_review} date(s)/section(s) read from scanned documents are not "
                "confirmed yet and are hidden. Do not guess them; say they need checking."
            )

    # Every DB read /chat needs is done — close explicitly rather than
    # wait for get_db()'s own teardown (which only runs once this whole
    # async function returns). llm.generate() below can take up to
    # settings.llm_timeout_s (120s default); holding this connection
    # checked out for that long would starve every other route's
    # Depends(get_db) out of the pool for as long as a reply is in
    # flight (see chat_generation.py's docstring). Session.close() is
    # idempotent, so get_db()'s later close() is a harmless no-op.
    db.close()

    try:
        draft = await generate_draft(case_details, documents, payload.message, llm)
    except LLMUnavailable:
        raise HTTPException(
            status_code=503,
            detail="NyayMitra AI is offline right now. Please try again in a minute.",
        )

    verdict = verify_draft(draft.text)

    return ChatResponse(
        text=draft.text,
        # verify_draft() always returns verified=False — no
        # document_faithfulness classifier exists to legitimately return
        # anything else (see its own docstring for why that's built in
        # there, not re-decided here).
        verificationStatus="verified" if verdict.verified else "unverified",
        citedSections=verdict.cited_sections,
        citedDocuments=cited_documents,
        skippedDocuments=skipped_documents,
        fieldsPendingReview=pending_review,
        modelUsed=draft.model,
        latencyMs=draft.latency_ms,
    )
