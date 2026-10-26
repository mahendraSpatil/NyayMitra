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
from .document_fields import fields_by_document, model_view_of
from ..pdf_extraction import STATUS_OCR_LOW_CONFIDENCE

# Character count, not tokens — crude, but this is a placeholder until
# generation_service exists and real model context limits matter.
CONTEXT_CHAR_BUDGET = 8000


@dataclass
class DocumentContext:
    doc_id: str
    doc_type: str
    text: str
    # 'text_layer' (exact) or 'ocr' (recognised from images, may contain
    # misread characters). Defaults keep older callers working.
    text_source: str = "text_layer"
    ocr_confidence: float | None = None


@dataclass
class ExcludedDocument:
    doc_id: str
    doc_type: str
    # Machine-readable, rendered by the client: 'low_ocr_confidence'.
    reason: str
    ocr_confidence: float | None = None


def fetch_case_document_context(db: Session, case_id: uuid.UUID) -> tuple[list[DocumentContext], bool]:
    """Returns (documents included, whether any were dropped for budget).

    Selection is chronological (uploaded_at ascending) — never "the
    newest document": a bail application, a remand order, and a charge
    sheet answer different questions, and picking only the latest upload
    would silently evict earlier ones.
    """
    documents = db.scalars(
        select(Document).where(Document.case_id == case_id).order_by(Document.uploaded_at.asc())
    ).all()
    fields = fields_by_document(db, case_id)

    included: list[DocumentContext] = []
    total_chars = 0
    truncated = False

    for doc in documents:
        text = doc.raw_text
        if not text:
            continue  # no_text_layer / failed / not yet processed — nothing to add
        if doc.ocr_status == STATUS_OCR_LOW_CONFIDENCE:
            # Stored (a human can still read it) but deliberately NOT
            # given to the model: OCR errors in a section number or a
            # custody date pass every automated check we have, so a scan
            # we aren't confident in is excluded rather than trusted.
            # Surfaced to the user via fetch_excluded_documents().
            continue
        # What the model may see: unconfirmed key fields and low-confidence
        # numbers masked, reviewer corrections applied. raw_text itself is
        # never modified (it's what the document actually says / was read as).
        text = model_view_of(doc, fields.get(doc.id, []))

        remaining = CONTEXT_CHAR_BUDGET - total_chars
        if remaining <= 0:
            truncated = True
            break  # budget genuinely exhausted — no later document fits either

        if len(text) > remaining:
            # This one document alone doesn't fit what's left of the
            # budget — include as much of it as fits rather than
            # dropping it (and, with the old `break` here, every
            # document after it too — including one this small that
            # would have fit easily) entirely. A single oversized
            # document ahead of it in upload order must never silently
            # evict everything behind it; that's this function's own
            # stated purpose above.
            included.append(
                DocumentContext(
                    doc_id=str(doc.id),
                    doc_type=doc.doc_type,
                    text=text[:remaining],
                    text_source=doc.text_source,
                    ocr_confidence=doc.ocr_confidence,
                )
            )
            total_chars += remaining
            truncated = True
            continue

        included.append(
            DocumentContext(
                doc_id=str(doc.id),
                doc_type=doc.doc_type,
                text=text,
                text_source=doc.text_source,
                ocr_confidence=doc.ocr_confidence,
            )
        )
        total_chars += len(text)

    return included, truncated


def fetch_excluded_documents(db: Session, case_id: uuid.UUID) -> list[ExcludedDocument]:
    """Documents with text that /chat deliberately did not use, so the
    answer can say "I couldn't use your scanned FIR" instead of silently
    answering without it."""
    documents = db.scalars(
        select(Document)
        .where(Document.case_id == case_id, Document.ocr_status == STATUS_OCR_LOW_CONFIDENCE)
        .order_by(Document.uploaded_at.asc())
    )
    return [
        ExcludedDocument(
            doc_id=str(d.id),
            doc_type=d.doc_type,
            reason="low_ocr_confidence",
            ocr_confidence=d.ocr_confidence,
        )
        for d in documents
    ]
