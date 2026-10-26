import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...db.models import CaseEvent
from ...dependencies import CurrentUser, require_case_manager, require_case_member
from ...models.v2.case_event import CaseEventItem, CaseEventRequest, CaseEventResponse
from ...services.v2.connections import manager as ws_manager

router = APIRouter()


@router.get("/cases/{case_id}/events", response_model=list[CaseEventItem])
def list_case_events(
    case_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_member),
    db: Session = Depends(get_db),
) -> list[CaseEventItem]:
    """Non-hearing timeline milestones — the other half of the merged
    Case Timeline the Flutter client builds from this endpoint plus
    GET /cases/{caseId}/hearings (see NyayMitra.md's Postgres schema
    notes on case_events). NULLS LAST: an event logged without a date
    isn't placeable chronologically among the dated ones, so it sorts
    after them rather than arbitrarily first.
    """
    events = db.scalars(
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .order_by(CaseEvent.event_date.asc().nulls_last())
    )
    return [
        CaseEventItem(id=str(e.id), title=e.title, date=e.event_date, eventType=e.event_type, done=e.done)
        for e in events
    ]


@router.post("/cases/{case_id}/events", response_model=CaseEventResponse)
def add_case_event(
    case_id: uuid.UUID,
    payload: CaseEventRequest,
    current_user: CurrentUser = Depends(require_case_manager),
    db: Session = Depends(get_db),
) -> CaseEventResponse:
    """Only a case manager can log a milestone — same authorization shape
    as adding a hearing (require_case_manager, not require_case_member):
    reading a case's history is everyone's; writing to it is the case
    manager's. Without this route case_events had no write path at all,
    so the table stayed empty forever and the timeline's non-hearing half
    was structurally dead.
    """
    event = CaseEvent(
        case_id=case_id,
        title=payload.title,
        event_date=payload.date,
        event_type=payload.eventType,
    )
    db.add(event)
    db.commit()
    ws_manager.broadcast_case_sync(case_id, {"type": "case_events_changed", "caseId": str(case_id)})
    return CaseEventResponse(eventId=str(event.id))
