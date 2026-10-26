from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    caseId: str | None = None


class CitedDocument(BaseModel):
    docId: str
    docType: str
    # 'text_layer' | 'ocr' — how the text the model saw was obtained.
    textSource: str = "text_layer"
    # 0-100; only for OCR'd scans.
    ocrConfidence: float | None = None


class SkippedDocument(BaseModel):
    """A document with text that was NOT given to the model, and why."""

    docId: str
    docType: str
    reason: str  # 'low_ocr_confidence'
    ocrConfidence: float | None = None


class ChatResponse(BaseModel):
    text: str
    verificationStatus: str = "unverified"
    citedSections: list[str] = Field(default_factory=list)
    citedDocuments: list[CitedDocument] = Field(default_factory=list)
    skippedDocuments: list[SkippedDocument] = Field(default_factory=list)
    # Key facts (dates, sections, FIR numbers) read from documents that are
    # still waiting for a person to confirm them — the model was NOT shown
    # these values. The UI says so, so a family knows why an answer is vague.
    fieldsPendingReview: int = 0
    # Optional, additive: existing clients ignore fields they don't parse
    # (see client/lib/features/chatbot/chat_service.dart). Useful for
    # debugging which provider actually answered, and this is what
    # section 9's future eval script (README_chat.md, not built here)
    # will want per-response latency for.
    modelUsed: str | None = None
    latencyMs: int | None = None
