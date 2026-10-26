"""Backfill key fields (FIR number, sections, dates) for documents that
were uploaded before field extraction existed. Idempotent: documents that
already have fields are skipped unless --force.

Text-layer documents get exact fields (auto-accepted unless a check
fails). Older OCR documents have no stored word confidences, so all of
their fields come back needs_review — a person confirms them, same as a
new upload.

Usage (from backend/, venv active):
    python scripts/extract_fields.py            # all documents without fields
    python scripts/extract_fields.py --force    # re-extract everything
                                                # (discards existing reviews!)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import Document, DocumentField
from app.services.pdf_extraction import ExtractionResult
from app.services.v2.document_fields import add_fields_for_document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-extract documents that already have fields")
    args = parser.parse_args()

    done = skipped = 0
    with SessionLocal() as db:
        for doc in db.scalars(select(Document).where(Document.raw_text.is_not(None))).all():
            has_fields = db.scalar(select(DocumentField.id).where(DocumentField.document_id == doc.id).limit(1))
            if has_fields and not args.force:
                skipped += 1
                continue
            if has_fields:
                db.query(DocumentField).filter(DocumentField.document_id == doc.id).delete()
            extraction = ExtractionResult(
                text=doc.raw_text,
                status=doc.ocr_status,
                text_source=doc.text_source if doc.text_source != "none" else "text_layer",
                confidence=doc.ocr_confidence,
            )
            rows = add_fields_for_document(
                db, doc, extraction, reference_date=doc.uploaded_at.date() if doc.uploaded_at else None
            )
            done += 1
            print(f"{doc.id} ({doc.doc_type}): {len(rows)} field(s), "
                  f"{sum(r.status == 'needs_review' for r in rows)} need review")
        db.commit()
    print(f"done: {done} document(s) processed, {skipped} skipped (already had fields)")


if __name__ == "__main__":
    main()
