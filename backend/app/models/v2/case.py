"""Same wire shape as the pre-migration Firestore-era case model on
purpose — the Flutter client's CaseService parses these exact field
names via Case.fromApi (client/lib/core/models/case.dart), which was
written to match this shape byte-for-byte.
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
    Case.fromApi exactly — advocateUid/advocateName/familyUids/
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
