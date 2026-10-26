from datetime import datetime

from pydantic import BaseModel, Field


class DocumentFieldItem(BaseModel):
    id: str
    documentId: str
    kind: str  # 'fir_number' | 'section' | 'date'
    # dates: 'arrest' | 'fir_registered' | 'hearing' | 'offence_date' | 'document_date'
    role: str | None
    label: str  # human-readable, e.g. "arrest date"
    rawText: str | None  # exactly as read from the document; None if added by hand
    extractedValue: str | None  # what the machine read (normalised); never overwritten
    value: str | None  # current value (reviewer's correction if any)
    displayValue: str
    confidence: float  # 0-100, weakest word in the field
    source: str  # 'text_layer' | 'ocr' | 'manual'
    extractor: str  # 'form' | 'pattern' | 'llm' | 'manual'
    roleBasis: str | None  # 'form_label' | 'keyword_near' | 'keyword_far' | 'doc_type' | 'llm' | 'reviewer'
    page: int | None
    issues: list[dict] = Field(default_factory=list)
    status: str  # 'auto_accepted' | 'needs_review' | 'confirmed' | 'rejected'
    reviewedRole: str | None = None
    reviewedAt: datetime | None = None


class MissingFact(BaseModel):
    """A fact this document type should contain that wasn't found."""

    kind: str
    role: str | None
    label: str


class ConfirmFieldRequest(BaseModel):
    # Omit to confirm what was read; send to correct it (validated per kind:
    # DD/MM/YYYY for dates, "436A CrPC" for sections, "214/2026" for FIRs).
    value: str | None = None
    # Dates only: correct what the date is for.
    role: str | None = None


class AddFieldRequest(BaseModel):
    kind: str
    role: str | None = None
    value: str


class FindFactsResponse(BaseModel):
    added: list[DocumentFieldItem]
    suggested: int  # how many the model proposed
    dropped: int  # proposals that didn't quote the document, or were already found
    unparseableReply: bool = False
