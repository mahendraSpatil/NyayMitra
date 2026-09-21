"""Postgres equivalent of app/services/case_document_context.py — fetches
a case's own uploaded documents with extracted text, for /chat to include
as context. Not retrieval_service from NyayMitra.md's AI pipeline (that's
a cross-encoder reranker over the case-law vector DB, a different,
still-unbuilt thing) — every document belonging to THIS case that has
usable extracted text, in upload order.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import Document

# Character count, not tokens — crude, but this is a placeholder until
# generation_service exists and real model context limits matter.
CONTEXT_CHAR_BUDGET = 8000


@dataclass
class DocumentContext:
    doc_id: str
    doc_type: str
    text: str


def fetch_case_document_context(db: Session, case_id: uuid.UUID) -> tuple[list[DocumentContext], bool]:
    """Returns (documents included, whether any were dropped for budget).

    Selection is chronological (uploaded_at ascending) — never "the
    newest document": a bail application, a remand order, and a charge
    sheet answer different questions, and picking only the latest upload
    would silently evict earlier ones.
    """
    documents = db.scalars(
        select(Document).where(Document.case_id == case_id).order_by(Document.uploaded_at.asc())
    )

    included: list[DocumentContext] = []
    total_chars = 0
    truncated = False

    for doc in documents:
        text = doc.raw_text
        if not text:
            continue  # no_text_layer / failed / not yet processed — nothing to add

        if total_chars + len(text) > CONTEXT_CHAR_BUDGET:
            truncated = True
            break

        included.append(DocumentContext(doc_id=str(doc.id), doc_type=doc.doc_type, text=text))
        total_chars += len(text)

    return included, truncated
