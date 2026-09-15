from fastapi import APIRouter, Request

from ..auth import get_firestore_db
from ..models.chat import ChatRequest, ChatResponse, CitedDocument
from ..services.case_access import authorize_case_access
from ..services.case_document_context import fetch_case_document_context

router = APIRouter()


def _uid(request: Request) -> str:
    return request.state.user.get("uid") or request.state.user.get("sub")


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
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
    #     CLAUDE.md's fail-closed rule, never stub this to return verified
    #     — including when the reply is grounded in real document text.
    #     Having context is not the same as having verified a claim
    #     against it.

    cited_documents: list[CitedDocument] = []
    context_note = ""

    if payload.caseId:
        db = get_firestore_db()
        # Independently authorized here too, not inherited from anywhere
        # else — an NGO account (or anyone unauthorized for this case)
        # passing a caseId they don't own must not leak that case's
        # document text through /chat as a side door around the read
        # rules that already protect direct Firestore access.
        authorize_case_access(db, payload.caseId, _uid(request))

        documents, truncated = fetch_case_document_context(db, payload.caseId)
        cited_documents = [
            CitedDocument(docId=d.doc_id, docType=d.doc_type) for d in documents
        ]

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
