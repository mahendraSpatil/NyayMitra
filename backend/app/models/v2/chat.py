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
