"""Fetches a case's own uploaded documents with extracted text, for /chat
to include as context. This is NOT retrieval_service from CLAUDE.md's AI
pipeline (that's a cross-encoder reranker over the case-law vector DB, for
past judgments — a different, still-unbuilt thing). This is simpler:
every document belonging to THIS case that has usable extracted text, in
upload order.
"""

from dataclasses import dataclass

# Character count, not tokens — crude, but this is a placeholder until
# generation_service exists and real model context limits matter. Bounds
# response size for now rather than tuning against an actual budget.
CONTEXT_CHAR_BUDGET = 8000


@dataclass
class DocumentContext:
    doc_id: str
    doc_type: str
    text: str


def fetch_case_document_context(db, case_id: str) -> tuple[list[DocumentContext], bool]:
    """Returns (documents included, whether any were dropped for budget).

    Selection is chronological (uploadedAt ascending) — never "the newest
    document": a bail application, a remand order, and a charge sheet
    answer different questions, and picking only the latest upload would
    silently evict earlier ones (e.g. a family uploading an ID proof would
    evict the bail order from context).
    """
    docs_ref = (
        db.collection("cases")
        .document(case_id)
        .collection("documents")
        .order_by("uploadedAt")
    )

    included: list[DocumentContext] = []
    total_chars = 0
    truncated = False

    for snap in docs_ref.stream():
        data = snap.to_dict() or {}
        text = data.get("rawText")
        if not text:
            continue  # no_text_layer / failed / not yet processed — nothing to add

        if total_chars + len(text) > CONTEXT_CHAR_BUDGET:
            truncated = True
            break

        included.append(
            DocumentContext(doc_id=snap.id, doc_type=data.get("docType", ""), text=text)
        )
        total_chars += len(text)

    return included, truncated
