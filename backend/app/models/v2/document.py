from datetime import datetime

from pydantic import BaseModel, Field

from .document_field import DocumentFieldItem, MissingFact


class SignUploadRequest(BaseModel):
    caseId: str
    docType: str


class SignUploadResponse(BaseModel):
    docId: str
    cloudName: str
    apiKey: str
    timestamp: int
    signature: str
    publicId: str
    resourceType: str = "raw"
    type: str = "authenticated"


class ConfirmUploadRequest(BaseModel):
    caseId: str
    docId: str
    docType: str
    publicId: str


class ConfirmUploadResponse(BaseModel):
    docId: str
    ocrStatus: str
    hasText: bool
    # 'text_layer' | 'ocr' | 'none' — see app/services/pdf_extraction.py.
    textSource: str = "none"
    # 0-100, only for OCR'd scans.
    ocrConfidence: float | None = None
    # True when the scan had more pages than OCR_MAX_PAGES: text is partial.
    ocrTruncated: bool = False
    # Key fields (dates/sections/FIR no.) a person must confirm before the
    # AI may rely on them.
    fieldsNeedingReview: int = 0


class DownloadUrlResponse(BaseModel):
    url: str
    expiresAt: int


class DocumentItem(BaseModel):
    """Matches client/lib/core/models/case_document.dart's
    CaseDocument.fromApi field names.
    """

    id: str
    docType: str
    storagePath: str | None
    uploadedBy: str | None
    uploadedAt: datetime | None
    ocrStatus: str | None
    rawText: str | None
    textSource: str = "none"
    ocrConfidence: float | None = None
    statutes: list = []
    fields: list[DocumentFieldItem] = Field(default_factory=list)
    # Facts this document type should contain that weren't found — shown
    # as "add it" prompts instead of failing silently.
    missingFacts: list[MissingFact] = Field(default_factory=list)
