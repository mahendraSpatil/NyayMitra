import time
import uuid

import cloudinary
import cloudinary.utils
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import settings
from ...db.base import get_db
from ...db.models import Case, Document
from ...dependencies import CurrentUser, require_case_member, require_case_member_from_body
from ...models.v2.document import (
    ConfirmUploadRequest,
    ConfirmUploadResponse,
    DocumentItem,
    DownloadUrlResponse,
    SignUploadRequest,
    SignUploadResponse,
)
from ...services.cloudinary_delivery import signed_download_url
from ...services.pdf_extraction import extract_document
from ...services.v2.connections import manager as ws_manager
from ...models.v2.document_field import MissingFact
from ...services.field_extraction import field_label
from ...services.v2.document_fields import (
    add_fields_for_document,
    document_missing_facts,
    fields_by_document,
)
from .document_fields import to_item as field_to_item

router = APIRouter()


@router.post("/documents/sign-upload", response_model=SignUploadResponse)
async def sign_upload(
    payload: SignUploadRequest,
    current_user: CurrentUser = Depends(require_case_member_from_body("caseId")),
    db: Session = Depends(get_db),
) -> SignUploadResponse:
    settings.require_cloudinary()

    # Reserves an ID without writing anything yet — the actual document
    # row is created in confirm_upload, once the file genuinely exists on
    # Cloudinary and its text has been extracted.
    doc_id = uuid.uuid4()
    public_id = f"cases/{payload.caseId}/documents/{doc_id}"
    timestamp = int(time.time())

    # type=authenticated is signed alongside public_id/timestamp — it must
    # be, since the client sends it back as an upload form field and
    # Cloudinary verifies the signature over everything it receives. An
    # "upload"-type asset (the default) is publicly fetchable by anyone
    # with the URL, and these are prisoners' case documents.
    params_to_sign = {
        "public_id": public_id,
        "timestamp": timestamp,
        "type": "authenticated",
    }
    signature = cloudinary.utils.api_sign_request(params_to_sign, settings.cloudinary_api_secret)

    return SignUploadResponse(
        docId=str(doc_id),
        cloudName=settings.cloudinary_cloud_name,
        apiKey=settings.cloudinary_api_key,
        timestamp=timestamp,
        signature=signature,
        publicId=public_id,
        resourceType="raw",
        type="authenticated",
    )


@router.post("/documents/confirm-upload", response_model=ConfirmUploadResponse)
async def confirm_upload(
    payload: ConfirmUploadRequest,
    current_user: CurrentUser = Depends(require_case_member_from_body("caseId")),
    db: Session = Depends(get_db),
) -> ConfirmUploadResponse:
    case_id = uuid.UUID(payload.caseId)

    # For resource_type=raw, Cloudinary appends the original file's
    # extension onto the public_id we chose at sign-upload time — the
    # actual assigned public_id is what the client's upload response
    # reported, not our pre-upload guess. Mint our own short-lived signed
    # URL to fetch it; never trust a URL the client hands us.
    download_url, _ = signed_download_url(payload.publicId)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(download_url, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"Could not download uploaded file: {exc}"
            ) from exc

    # Blocking and potentially slow for scans (OCR rasterises and reads
    # every page) — off the event loop so one upload can't freeze every
    # other request, including WebSocket traffic.
    extraction = await run_in_threadpool(extract_document, response.content)

    document = Document(
        id=uuid.UUID(payload.docId),
        case_id=case_id,
        doc_type=payload.docType,
        # The public_id, not a URL — a stored URL would be a permanent
        # bearer token for this document. Every future read goes through
        # /documents/{caseId}/{docId}/download-url, which re-authorizes
        # and mints a fresh short-lived URL.
        storage_path=payload.publicId,
        uploaded_by=current_user.id,
        ocr_status=extraction.status,
        raw_text=extraction.text,
        text_source=extraction.text_source,
        ocr_confidence=extraction.confidence,
        statutes=[],
    )
    db.add(document)
    db.flush()
    # Key facts (FIR number, sections, dates), each with its own
    # confidence and review status — see field_extraction.py.
    field_rows = add_fields_for_document(db, document, extraction)

    case = db.get(Case, case_id)
    case.document_count += 1

    db.commit()
    ws_manager.broadcast_case_sync(case_id, {"type": "documents_changed", "caseId": str(case_id)})

    return ConfirmUploadResponse(
        docId=payload.docId,
        ocrStatus=extraction.status,
        hasText=extraction.text is not None,
        textSource=extraction.text_source,
        ocrConfidence=extraction.confidence,
        ocrTruncated=extraction.truncated,
        fieldsNeedingReview=sum(1 for f in field_rows if f.status == "needs_review"),
    )


@router.get("/cases/{case_id}/documents", response_model=list[DocumentItem])
def list_documents(
    case_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_member),
    db: Session = Depends(get_db),
) -> list[DocumentItem]:
    documents = db.scalars(
        select(Document).where(Document.case_id == case_id).order_by(Document.uploaded_at.asc())
    ).all()
    fields = fields_by_document(db, case_id)
    return [
        DocumentItem(
            id=str(d.id),
            docType=d.doc_type,
            storagePath=d.storage_path,
            uploadedBy=str(d.uploaded_by),
            uploadedAt=d.uploaded_at,
            ocrStatus=d.ocr_status,
            rawText=d.raw_text,
            textSource=d.text_source,
            ocrConfidence=d.ocr_confidence,
            statutes=d.statutes,
            fields=[field_to_item(f) for f in fields.get(d.id, [])],
            missingFacts=[
                MissingFact(kind=kind, role=role, label=field_label(kind, role))
                for kind, role in document_missing_facts(d, fields.get(d.id, []))
            ],
        )
        for d in documents
    ]


@router.get("/documents/{case_id}/{doc_id}/download-url", response_model=DownloadUrlResponse)
async def get_download_url(
    case_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_member),
    db: Session = Depends(get_db),
) -> DownloadUrlResponse:
    """Mints a fresh short-lived signed URL for viewing/downloading a case
    document — re-authorized on every call, never cached or stored. This
    is the only sanctioned way to read a document's bytes after upload;
    an asset is never switched to public delivery to work around this.
    """
    document = db.get(Document, doc_id)
    if document is None or document.case_id != case_id:
        raise HTTPException(status_code=404, detail="Document not found")

    url, expires_at = signed_download_url(document.storage_path)
    return DownloadUrlResponse(url=url, expiresAt=expires_at)
