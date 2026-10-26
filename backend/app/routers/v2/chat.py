import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...db.models import Case
from ...dependencies import CurrentUser, require_case_member_from_body
from ...llm.base import LLMProvider, LLMUnavailable
from ...llm.factory import get_llm
from ...models.v2.chat import ChatRequest, ChatResponse, CitedDocument
from ...services.v2.case_document_context import fetch_case_document_context
from ...services.v2.chat_generation import generate_draft
from ...services.v2.verification import verify_draft

router = APIRouter()

# caseId is optional on this endpoint (the chatbot FAB is portal-home-level
# for Advocate/NGO, with no single case in scope there) — the membership
# check only applies when a caseId is actually present.
_require_optional_case_member = require_case_member_from_body("caseId", optional=True)

# TODO(ocr_service): still not connected — pdf_extraction.py (used by
#     /documents/confirm-upload) reads a PDF's existing text layer only.
#     A scanned document with no text layer still has nothing to
#     retrieve here.
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
    case_details: dict = {}
    cited_documents: list[CitedDocument] = []
    documents = []

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

        documents, _truncated = fetch_case_document_context(db, case_id)
        cited_documents = [
            CitedDocument(docId=d.doc_id, docType=d.doc_type) for d in documents
        ]

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
        modelUsed=draft.model,
        latencyMs=draft.latency_ms,
    )
