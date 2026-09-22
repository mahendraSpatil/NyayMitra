from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    caseId: str | None = None


class CitedDocument(BaseModel):
    docId: str
    docType: str


class ChatResponse(BaseModel):
    """Field names match the cases/{caseId}/messages/{messageId} schema
    (NyayMitra.md), not a backend-only convention — so the Flutter client can
    parse this straight into a ChatMessage-shaped value.

    citedDocuments is new: which of the case's documents were actually in
    context for this reply. Not the same thing as citedSections (specific
    statute sections, once law-grounding verification exists) — this is
    "what was in scope," independent of whether any claim was verified
    against it. Added now, ahead of document_faithfulness verification
    existing, because that check will need to know what was in scope to
    check claims against — retrofitting this after messages are already
    being persisted would be the wrong order to build it in.
    """

    text: str
    verificationStatus: str = "unverified"
    citedSections: list[str] = Field(default_factory=list)
    citedDocuments: list[CitedDocument] = Field(default_factory=list)
