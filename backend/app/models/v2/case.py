"""Same wire shape as app/models/case.py (the Firebase-era version) on
purpose — the Flutter client's existing CaseService parses these exact
field names. Step 5 of the Postgres migration only changes the base URL
it calls, not a line of its JSON handling, and that's only true if these
response shapes stay byte-for-byte identical to the ones it already
understands.
"""

from datetime import datetime

from pydantic import BaseModel


class CreateCaseRequest(BaseModel):
    undertrialName: str
    firNumber: str = ""
    court: str = ""


class CreateCaseResponse(BaseModel):
    caseId: str


class CaseItem(BaseModel):
    """One case, shaped to match client/lib/core/models/case.dart's
    Case.fromFirestore exactly — advocateUid/advocateName/familyUids/
    ngoUids are no longer columns on cases (case_members is the source of
    truth, commit 1), so these are joined at read time rather than
    denormalised again. timeline is always [] — cases.timeline doesn't
    exist in Postgres (dropped in favor of hearings + case_events,
    commit 1) and nothing has replaced it in the API yet; the Flutter
    model keeps the field so existing widgets don't need a signature
    change, it just never has anything in it post-cutover.
    """

    id: str
    firNumber: str
    court: str
    undertrialName: str
    advocateUid: str | None
    advocateName: str
    familyUids: list[str]
    ngoUids: list[str]
    createdBy: str
    ownerType: str
    stage: str
    stageLabel: str
    stageTone: str
    nextHearingDate: datetime | None
    documentCount: int
    timeline: list = []
