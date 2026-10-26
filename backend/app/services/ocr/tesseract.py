"""Tesseract implementation of OCRProvider.

pytesseract and pdf2image are only thin wrappers: the Tesseract and
poppler *binaries* must be installed separately (see README.md's OCR
section). Their absence surfaces as OCRUnavailable, never a stack trace.

Confidence comes from image_to_data (per word), not image_to_string,
because the single number that matters downstream is "how much should
anyone trust this text" — a wrong digit in a section number or a custody
date passes every automated check we have, so low-quality scans have to
be caught here, at the source.
"""

import logging
import threading
import time
from io import BytesIO

import pytesseract
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError
from pypdf import PdfReader
from pytesseract import Output, TesseractNotFoundError

from ...config import settings
from .base import OCRError, OCRProvider, OCRResult, OCRTimeout, OCRUnavailable, OCRWord

logger = logging.getLogger(__name__)

# Each Tesseract run is already CPU-heavy and a 300-DPI page is ~25 MB of
# pixels; two scans OCR'ing at once is plenty for a laptop-hosted demo.
_CONCURRENCY = threading.BoundedSemaphore(2)


class TesseractProvider(OCRProvider):
    name = "tesseract"

    def __init__(self) -> None:
        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        self._languages: str | None = None

    def _resolve_languages(self) -> str:
        """Requested languages that are actually installed. A missing
        language pack degrades to fewer languages (with a warning) rather
        than failing every upload — and a Devanagari scan read without
        `hin` comes back low-confidence, so it is gated, not trusted."""
        if self._languages is not None:
            return self._languages
        try:
            installed = set(pytesseract.get_languages(config=""))
        except TesseractNotFoundError as exc:
            raise OCRUnavailable(
                "Tesseract is not installed or not on PATH (set TESSERACT_CMD)."
            ) from exc
        requested = [l for l in settings.ocr_languages.split("+") if l]
        usable = [l for l in requested if l in installed]
        missing = [l for l in requested if l not in installed]
        if missing:
            logger.warning(
                "OCR language pack(s) not installed: %s — continuing with %s",
                ",".join(missing),
                "+".join(usable) or "none",
            )
        if not usable:
            raise OCRUnavailable(
                f"None of the OCR languages {requested} are installed in Tesseract."
            )
        self._languages = "+".join(usable)
        return self._languages

    def ocr_pdf(self, data: bytes) -> OCRResult:
        languages = self._resolve_languages()

        try:
            total_pages = len(PdfReader(BytesIO(data)).pages)
        except Exception as exc:
            raise OCRError(f"Could not read the PDF to count its pages: {exc}") from exc
        if total_pages == 0:
            raise OCRError("The PDF has no pages.")
        pages_to_read = min(total_pages, settings.ocr_max_pages)

        text = ""
        words: list[OCRWord] = []

        deadline = time.monotonic() + settings.ocr_max_seconds
        pages_done = 0
        with _CONCURRENCY:
            for page_no in range(1, pages_to_read + 1):
                if page_no > 1 and time.monotonic() > deadline:
                    # Overall time budget spent: stop and report the
                    # result as truncated rather than hang the upload.
                    logger.warning("OCR time budget hit after %d page(s)", pages_done)
                    break
                # One page at a time: keeps peak memory at a single
                # rasterised page instead of the whole document.
                try:
                    images = convert_from_bytes(
                        data,
                        dpi=settings.ocr_dpi,
                        first_page=page_no,
                        last_page=page_no,
                        poppler_path=settings.poppler_path or None,
                    )
                except PDFInfoNotInstalledError as exc:
                    raise OCRUnavailable(
                        "poppler is not installed or not on PATH (set POPPLER_PATH)."
                    ) from exc
                except (PDFPageCountError, PDFSyntaxError) as exc:
                    raise OCRError(f"Could not rasterise page {page_no}: {exc}") from exc
                if not images:
                    continue

                try:
                    ocr = pytesseract.image_to_data(
                        images[0],
                        lang=languages,
                        output_type=Output.DICT,
                        timeout=settings.ocr_page_timeout_s,
                    )
                except TesseractNotFoundError as exc:
                    raise OCRUnavailable(
                        "Tesseract is not installed or not on PATH (set TESSERACT_CMD)."
                    ) from exc
                except RuntimeError as exc:  # pytesseract's timeout error
                    raise OCRTimeout(f"OCR timed out on page {page_no}: {exc}") from exc
                finally:
                    for img in images:
                        img.close()

                pages_done += 1
                page_text, page_words = _page_from_data(ocr)
                if not page_text:
                    continue
                if text:
                    text += "\n\n"
                offset = len(text)
                text += page_text
                words.extend(
                    OCRWord(start=offset + s, end=offset + e, confidence=c, page=page_no)
                    for s, e, c in page_words
                )

        confidences = [w.confidence for w in words]
        confidence = sum(confidences) / len(confidences) if confidences else None
        return OCRResult(
            text=text,
            confidence=round(confidence, 1) if confidence is not None else None,
            pages_processed=pages_done,
            truncated=total_pages > pages_done,
            word_count=len(words),
            words=tuple(words),
        )


def _page_from_data(ocr: dict) -> tuple[str, list[tuple[int, int, float]]]:
    """Rebuilds text from image_to_data's word table, keeping line and
    paragraph structure (select_excerpt() splits on blank lines, so
    paragraphs must survive), and returns each word's (start, end,
    confidence) as character offsets into that page text.

    Rows with conf == -1 are layout rows (page/block/paragraph/line
    containers), not words, and are ignored — averaging them in would
    drag every score down.
    """
    paragraphs: dict[tuple, dict[tuple, list[tuple[str, float]]]] = {}

    for i, raw in enumerate(ocr["text"]):
        word = (raw or "").strip()
        try:
            conf = float(ocr["conf"][i])
        except (TypeError, ValueError):
            continue
        if not word or conf < 0:
            continue
        para_key = (ocr["block_num"][i], ocr["par_num"][i])
        line_key = (ocr["line_num"][i],)
        paragraphs.setdefault(para_key, {}).setdefault(line_key, []).append((word, conf))

    text = ""
    spans: list[tuple[int, int, float]] = []
    for p_index, para_key in enumerate(sorted(paragraphs)):
        if p_index:
            text += "\n\n"
        lines = paragraphs[para_key]
        for l_index, line_key in enumerate(sorted(lines)):
            if l_index:
                text += "\n"
            for w_index, (word, conf) in enumerate(lines[line_key]):
                if w_index:
                    text += " "
                spans.append((len(text), len(text) + len(word), conf))
                text += word
    return text, spans
