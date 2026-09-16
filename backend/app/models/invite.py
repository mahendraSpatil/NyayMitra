from datetime import datetime

from pydantic import BaseModel


class GenerateInviteResponse(BaseModel):
    code: str
    expiresAt: datetime


class RedeemInviteRequest(BaseModel):
    code: str


class RedeemInviteResponse(BaseModel):
    caseId: str
