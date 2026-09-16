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
    # "authenticated", never "upload" — an "upload"-type asset is publicly
    # fetchable by anyone with the URL, and these are prisoners' case
    # documents. Included here (not hardcoded client-side) so the value
    # the client sends always matches exactly what the signature was
    # computed over.
    type: str = "authenticated"


class ConfirmUploadRequest(BaseModel):
    caseId: str
    docId: str
    docType: str
    # Cloudinary's actual assigned public_id from the upload response —
    # for resource_type=raw it has the file extension appended, which the
    # backend's pre-upload guess (sign-upload's publicId) does not, so it
    # can't be reconstructed server-side. Safe to accept from the client:
    # unlike a download URL, a bare public_id grants no access on its own
    # — only a request signed with the backend's api_secret can fetch it.
    publicId: str


class ConfirmUploadResponse(BaseModel):
    docId: str
    ocrStatus: str
    hasText: bool


class DownloadUrlResponse(BaseModel):
    url: str
    expiresAt: int
