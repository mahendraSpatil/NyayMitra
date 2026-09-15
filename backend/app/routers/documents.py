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
    SignUploadRequest,
    SignUploadResponse,
)
from ..services.case_access import authorize_case_access
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

    params_to_sign = {"public_id": public_id, "timestamp": timestamp}
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
    )


@router.post("/documents/confirm-upload", response_model=ConfirmUploadResponse)
async def confirm_upload(payload: ConfirmUploadRequest, request: Request) -> ConfirmUploadResponse:
    db = get_firestore_db()
    # Re-authorized independently rather than trusting the earlier
    # sign-upload call — a separate HTTP request gets its own check.
    authorize_case_access(db, payload.caseId, _uid(request))

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(payload.secureUrl, timeout=30)
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
            "storagePath": payload.secureUrl,
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
