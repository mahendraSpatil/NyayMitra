import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...db.models import Hearing
from ...dependencies import CurrentUser, require_case_manager, require_case_member
from ...models.v2.hearing import HearingItem, HearingRequest, HearingResponse
from ...services.v2.connections import manager as ws_manager
from ...services.v2.hearings import recompute_next_hearing_date

router = APIRouter()


@router.get("/cases/{case_id}/hearings", response_model=list[HearingItem])
def list_hearings(
    case_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_member),
    db: Session = Depends(get_db),
) -> list[HearingItem]:
    """Didn't exist before the Postgres migration — the Flutter client
    read hearings straight from a Firestore stream. Any case member can
    read (require_case_member, not require_case_manager); only a manager
    can write (the three routes below).
    """
    hearings = db.scalars(select(Hearing).where(Hearing.case_id == case_id).order_by(Hearing.date.asc()))
    return [
        HearingItem(
            id=str(h.id), date=h.date, court=h.court, purpose=h.purpose, status=h.status, notes=h.notes
        )
        for h in hearings
    ]


@router.post("/cases/{case_id}/hearings", response_model=HearingResponse)
def add_hearing(
    case_id: uuid.UUID,
    payload: HearingRequest,
    current_user: CurrentUser = Depends(require_case_manager),
    db: Session = Depends(get_db),
) -> HearingResponse:
    hearing = Hearing(
        case_id=case_id,
        date=payload.date,
        court=payload.court,
        purpose=payload.purpose,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(hearing)
    db.flush()
    next_date = recompute_next_hearing_date(db, case_id)
    db.commit()
    # After commit, never before — a client that refetches on this
    # signal must see data that's actually there, not a write that then
    # rolled back.
    ws_manager.broadcast_case_sync(case_id, {"type": "hearings_changed", "caseId": str(case_id)})
    return HearingResponse(hearingId=str(hearing.id), nextHearingDate=next_date)


@router.put("/cases/{case_id}/hearings/{hearing_id}", response_model=HearingResponse)
def update_hearing(
    case_id: uuid.UUID,
    hearing_id: uuid.UUID,
    payload: HearingRequest,
    current_user: CurrentUser = Depends(require_case_manager),
    db: Session = Depends(get_db),
) -> HearingResponse:
    hearing = db.get(Hearing, hearing_id)
    if hearing is None or hearing.case_id != case_id:
        raise HTTPException(status_code=404, detail="Hearing not found")

    hearing.date = payload.date
    hearing.court = payload.court
    hearing.purpose = payload.purpose
    hearing.status = payload.status
    hearing.notes = payload.notes
    db.flush()  # autoflush is off (db/base.py) — recompute's SELECT must see this UPDATE first

    next_date = recompute_next_hearing_date(db, case_id)
    db.commit()
    ws_manager.broadcast_case_sync(case_id, {"type": "hearings_changed", "caseId": str(case_id)})
    return HearingResponse(hearingId=str(hearing.id), nextHearingDate=next_date)


@router.delete("/cases/{case_id}/hearings/{hearing_id}", response_model=HearingResponse)
def delete_hearing(
    case_id: uuid.UUID,
    hearing_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_manager),
    db: Session = Depends(get_db),
) -> HearingResponse:
    hearing = db.get(Hearing, hearing_id)
    if hearing is None or hearing.case_id != case_id:
        raise HTTPException(status_code=404, detail="Hearing not found")

    db.delete(hearing)
    db.flush()  # autoflush is off (db/base.py) — recompute's SELECT must see this DELETE first
    next_date = recompute_next_hearing_date(db, case_id)
    db.commit()
    ws_manager.broadcast_case_sync(case_id, {"type": "hearings_changed", "caseId": str(case_id)})
    return HearingResponse(hearingId=str(hearing_id), nextHearingDate=next_date)
