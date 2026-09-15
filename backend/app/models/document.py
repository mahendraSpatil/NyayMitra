from pydantic import BaseModel


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


class ConfirmUploadRequest(BaseModel):
    caseId: str
    docId: str
    docType: str
    secureUrl: str


class ConfirmUploadResponse(BaseModel):
    docId: str
    ocrStatus: str
    hasText: bool
