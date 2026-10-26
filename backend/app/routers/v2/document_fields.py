"""Review of key facts read from case documents — the "confirm before the
app relies on it" step — plus adding a missed fact by hand and asking the
model to look for more. See app/services/field_extraction.py.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...db.models import CaseMember, Document, DocumentField
from ...dependencies import CurrentUser, require_case_member, require_case_reviewer
from ...llm.base import LLMProvider, LLMUnavailable
from ...llm.factory import get_llm
from ...models.v2.document_field import (
    AddFieldRequest,
    ConfirmFieldRequest,
    DocumentFieldItem,
    FindFactsResponse,
)
from ...services.field_extraction import (
    BASIS_REVIEWER,
    DATE_ROLES,
    KIND_DATE,
    KINDS,
    STATUS_CONFIRMED,
    STATUS_REJECTED,
    STATUSES,
    InvalidFieldValue,
    check_timeline,
    display_value,
    field_label,
    normalise_user_value,
)
from ...services.v2.connections import manager as ws_manager
from ...services.v2.document_fields import (
    add_manual_field,
    case_context_dates,
    row_from_candidate,
)
from ...services.v2.llm_field_finder import find_more_facts

router = APIRouter()


def to_item(f: DocumentField) -> DocumentFieldItem:
    return DocumentFieldItem(
        id=str(f.id),
        documentId=str(f.document_id),
        kind=f.kind,
        role=f.role,
        label=field_label(f.kind, f.role),
        rawText=f.raw_text,
        extractedValue=f.extracted_value,
        value=f.value,
        displayValue=display_value(f.kind, f.value),
        confidence=f.confidence,
        source=f.source,
        extractor=f.extractor,
        roleBasis=f.role_basis,
        page=f.page,
        issues=f.issues or [],
        status=f.status,
        reviewedRole=f.reviewed_role,
        reviewedAt=f.reviewed_at,
    )


@router.get("/cases/{case_id}/document-fields", response_model=list[DocumentFieldItem])
def list_case_fields(
    case_id: uuid.UUID,
    status: str | None = Query(default=None),
    current_user: CurrentUser = Depends(require_case_member),
    db: Session = Depends(get_db),
) -> list[DocumentFieldItem]:
    """All key facts on a case; ?status=needs_review is the review queue."""
    query = select(DocumentField).where(DocumentField.case_id == case_id)
    if status is not None:
        if status not in STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of {list(STATUSES)}")
        query = query.where(DocumentField.status == status)
    # Weakest first: the facts most likely to be wrong are reviewed first.
    rows = db.scalars(query.order_by(DocumentField.confidence.asc(), DocumentField.created_at.asc()))
    return [to_item(f) for f in rows]


def _get_field(db: Session, case_id: uuid.UUID, field_id: uuid.UUID) -> DocumentField:
    field = db.get(DocumentField, field_id)
    if field is None or field.case_id != case_id:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


def _get_document(db: Session, case_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.case_id != case_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _member_role(db: Session, case_id: uuid.UUID, user: CurrentUser) -> str | None:
    member = db.get(CaseMember, {"case_id": case_id, "user_id": user.id})
    return member.role if member else None


def _mark_reviewed(db: Session, field: DocumentField, case_id: uuid.UUID, user: CurrentUser) -> None:
    field.reviewed_by = user.id
    field.reviewed_role = _member_role(db, case_id, user)
    field.reviewed_at = datetime.now(timezone.utc)


def _changed(case_id: uuid.UUID) -> None:
    ws_manager.broadcast_case_sync(case_id, {"type": "documents_changed", "caseId": str(case_id)})


@router.post("/cases/{case_id}/document-fields/{field_id}/confirm", response_model=DocumentFieldItem)
async def confirm_field(
    case_id: uuid.UUID,
    field_id: uuid.UUID,
    payload: ConfirmFieldRequest,
    current_user: CurrentUser = Depends(require_case_reviewer),
    db: Session = Depends(get_db),
) -> DocumentFieldItem:
    """Confirm what was read (value AND what it is — the label shown), or
    correct it. Confirmation is the only way an OCR'd or AI-suggested fact
    becomes usable by the chat model."""
    field = _get_field(db, case_id, field_id)

    if payload.role is not None:
        if field.kind != KIND_DATE or payload.role not in DATE_ROLES:
            raise HTTPException(status_code=422, detail=f"role must be one of {list(DATE_ROLES)} (dates only)")
        field.role = payload.role

    if payload.value is not None:
        try:
            field.value = normalise_user_value(field.kind, payload.value)
        except InvalidFieldValue as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif field.value is None:
        raise HTTPException(
            status_code=422,
            detail="This field couldn't be read — enter the correct value to confirm it.",
        )

    if field.kind == KIND_DATE and field.role is not None:
        field.role_basis = BASIS_REVIEWER  # a person looked at the label and agreed
    field.status = STATUS_CONFIRMED
    _mark_reviewed(db, field, case_id, current_user)
    db.commit()
    db.refresh(field)
    _changed(case_id)
    return to_item(field)


@router.post("/cases/{case_id}/document-fields/{field_id}/reject", response_model=DocumentFieldItem)
async def reject_field(
    case_id: uuid.UUID,
    field_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_reviewer),
    db: Session = Depends(get_db),
) -> DocumentFieldItem:
    """For "this is wrong and I can't say what it should be", or "this
    isn't a real date/section at all". The field stays masked for the
    model and stops counting as pending review."""
    field = _get_field(db, case_id, field_id)
    field.status = STATUS_REJECTED
    _mark_reviewed(db, field, case_id, current_user)
    db.commit()
    db.refresh(field)
    _changed(case_id)
    return to_item(field)


@router.post("/cases/{case_id}/documents/{document_id}/fields", response_model=DocumentFieldItem)
async def add_field(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: AddFieldRequest,
    current_user: CurrentUser = Depends(require_case_reviewer),
    db: Session = Depends(get_db),
) -> DocumentFieldItem:
    """Add a fact the extractors missed, typed in from the paper original
    (e.g. "We couldn't find the arrest date — add it")."""
    document = _get_document(db, case_id, document_id)
    if payload.kind not in KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {list(KINDS)}")
    if payload.kind == KIND_DATE:
        if payload.role is not None and payload.role not in DATE_ROLES:
            raise HTTPException(status_code=422, detail=f"role must be one of {list(DATE_ROLES)}")
    elif payload.role is not None:
        raise HTTPException(status_code=422, detail="role applies to dates only")
    try:
        value = normalise_user_value(payload.kind, payload.value)
    except InvalidFieldValue as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = add_manual_field(
        db, document, kind=payload.kind, role=payload.role, value=value,
        user_id=current_user.id, member_role=_member_role(db, case_id, current_user),
    )
    db.commit()
    db.refresh(row)
    _changed(case_id)
    return to_item(row)


@router.post("/cases/{case_id}/documents/{document_id}/find-facts", response_model=FindFactsResponse)
async def find_facts(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_reviewer),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm),
) -> FindFactsResponse:
    """Ask the model to point at facts the form/pattern passes missed.
    Suggestions are kept only if they quote the document verbatim; all
    need review. Slow on a CPU-only local model — the client allows for
    it, same as /chat."""
    document = _get_document(db, case_id, document_id)
    if not document.raw_text or document.text_source not in ("text_layer", "ocr"):
        raise HTTPException(status_code=422, detail="This document has no readable text to search.")
    text, text_source = document.raw_text, document.text_source
    existing = list(db.scalars(select(DocumentField).where(DocumentField.document_id == document_id)))
    taken = [(f.span_start, f.span_end) for f in existing if f.span_start is not None]
    already = [f"{field_label(f.kind, f.role)}: {f.raw_text or display_value(f.kind, f.value)}" for f in existing]
    # Same reason as /chat: don't hold a pooled connection for the length
    # of a model call. The session reconnects on next use.
    db.close()

    try:
        found = await find_more_facts(llm, text=text, text_source=text_source, already_found=already, taken=taken)
    except LLMUnavailable:
        raise HTTPException(status_code=503, detail="NyayMitra AI is offline right now. Please try again in a minute.")

    document = _get_document(db, case_id, document_id)
    check_timeline(found.added, case_context_dates(db, case_id))
    rows = [row_from_candidate(document, f, text_source) for f in found.added]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    if rows:
        _changed(case_id)
    return FindFactsResponse(
        added=[to_item(r) for r in rows],
        suggested=found.suggested,
        dropped=found.dropped,
        unparseableReply=found.unparseable_reply,
    )
