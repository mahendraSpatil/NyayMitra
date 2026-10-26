from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    caseId: str | None = None


class CitedDocument(BaseModel):
    docId: str
    docType: str


class ChatResponse(BaseModel):
    text: str
    verificationStatus: str = "unverified"
    citedSections: list[str] = Field(default_factory=list)
    citedDocuments: list[CitedDocument] = Field(default_factory=list)
    # Optional, additive: existing clients ignore fields they don't parse
    # (see client/lib/features/chatbot/chat_service.dart). Useful for
    # debugging which provider actually answered, and this is what
    # section 9's future eval script (README_chat.md, not built here)
    # will want per-response latency for.
    modelUsed: str | None = None
    latencyMs: int | None = None
