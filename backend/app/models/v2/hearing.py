from datetime import datetime

from pydantic import BaseModel


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


class HearingItem(BaseModel):
    """One row of GET /cases/{caseId}/hearings — this endpoint didn't
    exist before the Postgres migration (the Flutter client read
    hearings straight from a Firestore stream); field names match
    client/lib/core/models/hearing.dart's Hearing.fromFirestore exactly,
    since that's what will parse this once step 5 switches the client
    over.
    """

    id: str
    date: datetime | None
    court: str
    purpose: str
    status: str
    notes: str
