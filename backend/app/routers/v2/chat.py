import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...dependencies import CurrentUser, require_case_member_from_body
from ...models.v2.chat import ChatRequest, ChatResponse, CitedDocument
from ...services.v2.case_document_context import fetch_case_document_context

router = APIRouter()

# caseId is optional on this endpoint (the chatbot FAB is portal-home-level
# for Advocate/NGO, with no single case in scope there) — the membership
# check only applies when a caseId is actually present.
_require_optional_case_member = require_case_member_from_body("caseId", optional=True)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: CurrentUser = Depends(_require_optional_case_member),
    db: Session = Depends(get_db),
) -> ChatResponse:
    # TODO(ocr_service): still not connected — pdf_extraction.py (used by
    #     /documents/confirm-upload) reads a PDF's existing text layer
    #     only. A scanned document with no text layer still has nothing
    #     to retrieve here.
    # TODO(ner_service): no jurisdiction/statute extraction yet.
    # TODO(retrieval_service): no case-law retrieval yet — that's a
    #     cross-encoder reranker over past judgments, separate from the
    #     case's own documents fetched below.
    # TODO(generation_service): no Gemini/Mistral call yet — the text
    #     below is a hardcoded placeholder, not a model response, even
    #     when real document context is included.
    # TODO(translation_service): no Bhashini translation yet.
    # TODO(verification_service): always unverified until both law
    #     grounding and document faithfulness are implemented. Per
    #     NyayMitra.md's fail-closed rule, never stub this to return
    #     verified — including when the reply is grounded in real
    #     document text. Having context is not the same as having
    #     verified a claim against it.

    cited_documents: list[CitedDocument] = []
    context_note = ""

    if payload.caseId:
        documents, truncated = fetch_case_document_context(db, uuid.UUID(payload.caseId))
        cited_documents = [CitedDocument(docId=d.doc_id, docType=d.doc_type) for d in documents]

        if documents:
            doc_list = ", ".join(f"{d.doc_type} ({d.doc_id})" for d in documents)
            context_note = f" Retrieved context from: {doc_list}."
            if truncated:
                context_note += (
                    " (Some documents were left out to stay within the context budget.)"
                )
        else:
            context_note = " No case documents with extracted text were found for this case yet."

    return ChatResponse(
        text=(
            f"You asked: \"{payload.message}\". This is a placeholder reply "
            "from NyayMitra AI's stub service — the real verification "
            "pipeline isn't connected yet. Please confirm anything "
            f"important with your advocate.{context_note}"
        ),
        verificationStatus="unverified",
        citedSections=[],
        citedDocuments=cited_documents,
    )
