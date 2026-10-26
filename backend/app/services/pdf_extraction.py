"""Turns an uploaded PDF into text, and records HOW that text was
obtained.

Two sources, never blurred together:
- text_layer: the PDF's own embedded text (pypdf). Exact.
- ocr: recognised from page images (app/services/ocr/). Probabilistic —
  a misread digit in a section number or custody date looks exactly like
  a correct one to every downstream check, so OCR text carries a
  confidence score and is gated on it (see OCR_MIN_CONFIDENCE).

Statuses (documents.ocr_status):
  extracted         text layer found
  ocr_extracted     scanned; OCR confidence >= OCR_MIN_CONFIDENCE
  ocr_low_confidence scanned; OCR ran but confidence is below threshold
                    (or no words were recognised). Text is stored for a
                    human to look at but is NOT given to the chat model.
  no_text_layer     scanned and OCR is unavailable/disabled
  failed            file unreadable or OCR crashed

Scope: printed/typed scans. Handwriting is expected to land in
ocr_low_confidence.
"""

import logging
from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader

from ..config import settings
from .ocr import OCRError, OCRTimeout, OCRUnavailable, OCRWord, get_ocr_provider

logger = logging.getLogger(__name__)

STATUS_EXTRACTED = "extracted"
STATUS_OCR_EXTRACTED = "ocr_extracted"
STATUS_OCR_LOW_CONFIDENCE = "ocr_low_confidence"
STATUS_NO_TEXT_LAYER = "no_text_layer"
STATUS_FAILED = "failed"

SOURCE_TEXT_LAYER = "text_layer"
SOURCE_OCR = "ocr"
SOURCE_NONE = "none"

# Statuses whose text may be handed to the chat model as document context.
CHAT_USABLE_STATUSES = (STATUS_EXTRACTED, STATUS_OCR_EXTRACTED)


@dataclass(frozen=True)
class ExtractionResult:
    text: str | None
    status: str
    text_source: str
    confidence: float | None = None
    truncated: bool = False
    # OCR word spans (offsets into `text`) — used for per-field confidence,
    # not persisted. Empty for text-layer documents.
    words: tuple[OCRWord, ...] = field(default=(), repr=False)


def extract_document(data: bytes) -> ExtractionResult:
    """Blocking (OCR is CPU-heavy) — call via run_in_threadpool."""
    try:
        reader = PdfReader(BytesIO(data))
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return ExtractionResult(None, STATUS_FAILED, SOURCE_NONE)

    text = "\n".join(pages_text).strip()
    if text:
        return ExtractionResult(text, STATUS_EXTRACTED, SOURCE_TEXT_LAYER)

    # No text layer: a scan. Try OCR if it's available.
    provider = get_ocr_provider()
    if provider is None:
        return ExtractionResult(None, STATUS_NO_TEXT_LAYER, SOURCE_NONE)

    try:
        result = provider.ocr_pdf(data)
    except OCRUnavailable as exc:
        logger.warning("OCR unavailable, leaving scan as no_text_layer: %s", exc)
        return ExtractionResult(None, STATUS_NO_TEXT_LAYER, SOURCE_NONE)
    except OCRTimeout as exc:
        # The engine thrashed on a degraded page: an unreadable scan, not
        # a broken file. Same outcome and same advice as low confidence.
        logger.warning("OCR timed out, treating as unreadable scan: %s", exc)
        return ExtractionResult(None, STATUS_OCR_LOW_CONFIDENCE, SOURCE_OCR, confidence=0.0)
    except OCRError as exc:
        logger.warning("OCR failed: %s", exc)
        return ExtractionResult(None, STATUS_FAILED, SOURCE_NONE)

    confidence = result.confidence if result.confidence is not None else 0.0
    ocr_text = result.text or None
    if ocr_text and result.truncated:
        # Partial text must never read as the whole document: a chat
        # answer of "the document doesn't mention X" would be wrong if X
        # is on page 25. The marker travels with the text everywhere it
        # goes (DB, document viewer, chat context).
        ocr_text += (
            f"\n\n[Scan continues — only the first {result.pages_processed} "
            "pages were read.]"
        )
    status = (
        STATUS_OCR_EXTRACTED
        if ocr_text and confidence >= settings.ocr_min_confidence
        else STATUS_OCR_LOW_CONFIDENCE
    )
    return ExtractionResult(
        text=ocr_text,
        status=status,
        text_source=SOURCE_OCR,
        confidence=confidence,
        truncated=result.truncated,
        words=result.words if ocr_text else (),
    )
