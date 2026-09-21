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


class DownloadUrlResponse(BaseModel):
    url: str
    expiresAt: int
