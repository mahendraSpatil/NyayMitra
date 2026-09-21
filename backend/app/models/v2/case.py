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
