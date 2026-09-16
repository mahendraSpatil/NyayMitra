import time

import cloudinary
import cloudinary.utils
import httpx
from fastapi import APIRouter, HTTPException, Request
from firebase_admin import firestore as firebase_firestore

from ..auth import get_firestore_db
from ..config import settings
from ..models.document import (
    ConfirmUploadRequest,
    ConfirmUploadResponse,
    DownloadUrlResponse,
    SignUploadRequest,
    SignUploadResponse,
)
from ..services.case_access import authorize_case_access
from ..services.cloudinary_delivery import signed_download_url
from ..services.pdf_extraction import extract_text

router = APIRouter()


def _uid(request: Request) -> str:
    return request.state.user.get("uid") or request.state.user.get("sub")


@router.post("/documents/sign-upload", response_model=SignUploadResponse)
async def sign_upload(payload: SignUploadRequest, request: Request) -> SignUploadResponse:
    settings.require_cloudinary()
    db = get_firestore_db()
    authorize_case_access(db, payload.caseId, _uid(request))

    # Reserves an ID without writing anything yet — the actual document
    # record is created in confirm_upload, once the file genuinely exists
    # on Cloudinary and its text has been extracted.
    doc_ref = db.collection("cases").document(payload.caseId).collection("documents").document()
    public_id = f"cases/{payload.caseId}/documents/{doc_ref.id}"
    timestamp = int(time.time())

    # type=authenticated is signed alongside public_id/timestamp — it must
    # be, since the client sends it back as an upload form field and
    # Cloudinary verifies the signature over everything it receives. An
    # "upload"-type asset (the default) is publicly fetchable by anyone
    # with the URL; these are prisoners' case documents.
    params_to_sign = {
        "public_id": public_id,
        "timestamp": timestamp,
        "type": "authenticated",
    }
    signature = cloudinary.utils.api_sign_request(
        params_to_sign, settings.cloudinary_api_secret
    )

    return SignUploadResponse(
        docId=doc_ref.id,
        cloudName=settings.cloudinary_cloud_name,
        apiKey=settings.cloudinary_api_key,
        timestamp=timestamp,
        signature=signature,
        publicId=public_id,
        resourceType="raw",
        type="authenticated",
    )


@router.post("/documents/confirm-upload", response_model=ConfirmUploadResponse)
async def confirm_upload(payload: ConfirmUploadRequest, request: Request) -> ConfirmUploadResponse:
    db = get_firestore_db()
    # Re-authorized independently rather than trusting the earlier
    # sign-upload call — a separate HTTP request gets its own check.
    authorize_case_access(db, payload.caseId, _uid(request))

    # For resource_type=raw, Cloudinary appends the original file's
    # extension onto the public_id we chose at sign-upload time — the
    # actual assigned public_id is what the client's upload response
    # reported, not our pre-upload guess. Mint our own short-lived signed
    # URL to fetch it; never trust a URL the client hands us (that was
    # the bug: a plain secure_url is either publicly fetchable — wrong —
    # or, for an authenticated asset, simply 401s without the signature
    # only the backend's api_secret can produce).
    download_url, _ = signed_download_url(payload.publicId)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(download_url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"Could not download uploaded file: {exc}"
            ) from exc

    raw_text, ocr_status = extract_text(response.content)

    doc_ref = (
        db.collection("cases")
        .document(payload.caseId)
        .collection("documents")
        .document(payload.docId)
    )
    doc_ref.set(
        {
            "docType": payload.docType,
            # The public_id, not a URL — a stored URL would be a
            # permanent bearer token for this document. Every future read
            # goes through /documents/{caseId}/{docId}/download-url,
            # which re-authorizes and mints a fresh short-lived URL.
            "storagePath": payload.publicId,
            "uploadedBy": _uid(request),
            "uploadedAt": firebase_firestore.SERVER_TIMESTAMP,
            "ocrStatus": ocr_status,
            "rawText": raw_text,
            "statutes": [],
        }
    )

    case_ref = db.collection("cases").document(payload.caseId)
    case_ref.update({"documentCount": firebase_firestore.Increment(1)})

    return ConfirmUploadResponse(
        docId=payload.docId,
        ocrStatus=ocr_status,
        hasText=raw_text is not None,
    )


@router.get("/documents/{case_id}/{doc_id}/download-url", response_model=DownloadUrlResponse)
async def get_download_url(case_id: str, doc_id: str, request: Request) -> DownloadUrlResponse:
    """Mints a fresh short-lived signed URL for viewing/downloading a case
    document — re-authorized on every call, never cached or stored. This
    is the only sanctioned way to read a document's bytes after upload;
    an asset is never switched to public delivery to work around this.
    """
    db = get_firestore_db()
    authorize_case_access(db, case_id, _uid(request))

    doc_snap = (
        db.collection("cases").document(case_id).collection("documents").document(doc_id).get()
    )
    if not doc_snap.exists:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = (doc_snap.to_dict() or {}).get("storagePath")
    if not storage_path:
        raise HTTPException(status_code=404, detail="Document has no stored file")

    url, expires_at = signed_download_url(storage_path)
    return DownloadUrlResponse(url=url, expiresAt=expires_at)
