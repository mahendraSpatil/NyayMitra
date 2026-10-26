"""Persistence and read-side for document key fields — the DB half of
app/services/field_extraction.py (which is pure and DB-free).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import settings
from ...db.models import Document, DocumentField
from ..field_extraction import (
    BASIS_REVIEWER,
    CASE_KEY_FACTS,
    EXTRACTOR_MANUAL,
    KIND_DATE,
    STATUS_CONFIRMED,
    STATUS_NEEDS_REVIEW,
    STATUS_REJECTED,
    USABLE_STATUSES,
    ContextDate,
    FieldCandidate,
    StoredField,
    WordSpan,
    display_value,
    extract_fields,
    field_label,
    missing_facts,
    render_for_model,
)
from ..pdf_extraction import ExtractionResult


def case_context_dates(
    db: Session, case_id: uuid.UUID, *, exclude_document: uuid.UUID | None = None
) -> list[ContextDate]:
    """Date facts already on the case (not rejected, with a value and a
    role) — for the cross-document timeline check."""
    query = select(DocumentField).where(
        DocumentField.case_id == case_id,
        DocumentField.kind == KIND_DATE,
        DocumentField.status != STATUS_REJECTED,
        DocumentField.value.is_not(None),
        DocumentField.role.is_not(None),
    )
    if exclude_document is not None:
        query = query.where(DocumentField.document_id != exclude_document)
    return [ContextDate(f.role, date.fromisoformat(f.value)) for f in db.scalars(query)]


def row_from_candidate(document: Document, f: FieldCandidate, source: str) -> DocumentField:
    return DocumentField(
        id=uuid.uuid4(),
        document_id=document.id,
        case_id=document.case_id,
        kind=f.kind,
        role=f.role,
        raw_text=f.raw_text,
        extracted_value=f.value,
        value=f.value,
        confidence=f.confidence,
        source=source,
        extractor=f.extractor,
        role_basis=f.role_basis,
        page=f.page,
        span_start=f.start,
        span_end=f.end,
        issues=f.issues,
        status=f.status,
    )


def add_fields_for_document(
    db: Session, document: Document, extraction: ExtractionResult, *, reference_date: date | None = None
) -> list[DocumentField]:
    """Runs field extraction over a freshly extracted document and adds
    the rows (and the document's masked-number spans) to the session.
    Caller commits. No-op for documents without text."""
    if not extraction.text or extraction.text_source not in ("text_layer", "ocr"):
        return []
    words = [WordSpan(w.start, w.end, w.confidence, w.page) for w in extraction.words]
    result = extract_fields(
        extraction.text,
        text_source=extraction.text_source,
        words=words,
        document_status=extraction.status,
        doc_type=document.doc_type,
        reference_date=reference_date,
        context_dates=case_context_dates(db, document.case_id, exclude_document=document.id),
        auto_accept_confidence=settings.ocr_field_auto_accept,
        uncertain_word_confidence=settings.ocr_uncertain_word_confidence,
        mask_all_numbers=settings.ocr_mask_all_numbers,
    )
    document.uncertain_spans = result.uncertain_spans
    rows = [row_from_candidate(document, f, extraction.text_source) for f in result.fields]
    db.add_all(rows)
    return rows


def add_manual_field(
    db: Session, document: Document, *, kind: str, role: str | None, value: str,
    user_id: uuid.UUID, member_role: str | None,
) -> DocumentField:
    """A fact a reviewer typed in from the paper original — for a required
    fact the extractor didn't find. Confirmed by definition; has no span
    in the text. `value` must already be normalised (normalise_user_value)."""
    row = DocumentField(
        id=uuid.uuid4(),
        document_id=document.id,
        case_id=document.case_id,
        kind=kind,
        role=role,
        raw_text=None,
        extracted_value=None,
        value=value,
        confidence=100.0,
        source="manual",
        extractor=EXTRACTOR_MANUAL,
        role_basis=BASIS_REVIEWER if role else None,
        page=None,
        span_start=None,
        span_end=None,
        issues=[],
        status=STATUS_CONFIRMED,
        reviewed_by=user_id,
        reviewed_role=member_role,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    return row


def model_view_of(document: Document, fields: list[DocumentField]) -> str:
    """raw_text as the chat model may see it — unconfirmed fields and
    masked numbers hidden, confirmed corrections applied."""
    return render_for_model(
        document.raw_text or "",
        [StoredField(f.kind, f.role, f.status, f.value, f.span_start, f.span_end) for f in fields],
        document.uncertain_spans or [],
    )


def fields_by_document(db: Session, case_id: uuid.UUID) -> dict[uuid.UUID, list[DocumentField]]:
    rows = db.scalars(
        select(DocumentField)
        .where(DocumentField.case_id == case_id)
        .order_by(DocumentField.document_id, DocumentField.span_start.nulls_last())
    )
    grouped: dict[uuid.UUID, list[DocumentField]] = {}
    for row in rows:
        grouped.setdefault(row.document_id, []).append(row)
    return grouped


def document_missing_facts(document: Document, fields: list[DocumentField]) -> list[tuple[str, str | None]]:
    if not document.raw_text:
        return []  # nothing could be read at all — the document status says so
    return missing_facts(document.doc_type, [(f.kind, f.role, f.status) for f in fields])


@dataclass
class CaseFacts:
    # Usable facts only (auto_accepted from exact text, or confirmed by a
    # person), deduplicated — what the model is told as fact.
    facts: list[dict]
    pending_review: int
    # Key facts (CASE_KEY_FACTS) with no usable or pending field anywhere
    # on the case — the model is told these are not in the documents.
    not_found: list[str]


def case_facts(db: Session, case_id: uuid.UUID) -> CaseFacts:
    rows = db.execute(
        select(DocumentField, Document.doc_type)
        .join(Document, Document.id == DocumentField.document_id)
        .where(DocumentField.case_id == case_id)
        .order_by(Document.uploaded_at.asc(), DocumentField.span_start.nulls_last())
    ).all()

    facts: list[dict] = []
    seen: set[tuple] = set()
    pending = 0
    present: set[tuple[str, str | None]] = set()
    for field, doc_type in rows:
        if field.status == STATUS_NEEDS_REVIEW:
            pending += 1
            present.add((field.kind, field.role))
            continue
        if field.status not in USABLE_STATUSES or field.value is None:
            continue
        present.add((field.kind, field.role))
        key = (field.kind, field.role, field.value)
        if key in seen:
            continue
        seen.add(key)
        if field.status == STATUS_CONFIRMED:
            who = field.reviewed_role or "a case member"
            basis = f"added by {who} from the original" if field.extractor == EXTRACTOR_MANUAL else f"confirmed by {who}"
        else:
            basis = "typed text in the document"
        facts.append(
            {
                "fact": field_label(field.kind, field.role),
                "value": display_value(field.kind, field.value),
                "from": doc_type,
                "basis": basis,
            }
        )

    not_found = [
        field_label(kind, role)
        for kind, role in CASE_KEY_FACTS
        if not any(k == kind and (role is None or r == role) for k, r in present)
    ]
    return CaseFacts(facts=facts, pending_review=pending, not_found=not_found)
