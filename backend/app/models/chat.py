from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    """Field names match the cases/{caseId}/messages/{messageId} schema
    (CLAUDE.md), not a backend-only convention — so the Flutter client can
    parse this straight into a ChatMessage-shaped value.
    """

    text: str
    verificationStatus: str = "unverified"
    citedSections: list[str] = Field(default_factory=list)
