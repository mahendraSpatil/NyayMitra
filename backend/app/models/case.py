from datetime import datetime

from pydantic import BaseModel


class CreateCaseRequest(BaseModel):
    undertrialName: str
    firNumber: str = ""
    court: str = ""


class CreateCaseResponse(BaseModel):
    caseId: str


class HearingRequest(BaseModel):
    date: datetime
    court: str = ""
    purpose: str = ""
    # 'scheduled' | 'completed' | 'adjourned' | 'cancelled' — nextHearingDate
    # is recomputed from whichever hearings are still 'scheduled'.
    status: str = "scheduled"
    notes: str = ""


class HearingResponse(BaseModel):
    hearingId: str
    nextHearingDate: datetime | None
