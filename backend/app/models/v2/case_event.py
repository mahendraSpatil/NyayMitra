from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Matches app/db/models.py's CaseEvent.event_type CHECK constraint
# exactly, so a bad value 422s here rather than reaching the DB.
EventType = Literal[
    "charge_sheet_filed", "bail_application_submitted", "bail_order_issued", "remand_extended", "other"
]


class CaseEventRequest(BaseModel):
    title: str
    date: datetime | None = None
    eventType: EventType = "other"


class CaseEventResponse(BaseModel):
    eventId: str


class CaseEventItem(BaseModel):
    """One row of GET /cases/{caseId}/events — field names match
    client/lib/core/models/case_event.dart's CaseEvent.fromApi exactly.
    """

    id: str
    title: str
    date: datetime | None
    eventType: str
    done: bool
