"""OCR provider interface — same swappable shape as DocumentStorage and
app/llm/: callers depend on OCRProvider, never on Tesseract directly, so
moving to PaddleOCR or a cloud OCR later is a new class plus one line in
factory.py, not a rewrite.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class OCRError(Exception):
    """The scan could not be OCR'd (corrupt file, engine crashed, a page
    timed out). Reported to the user as an extraction failure."""


class OCRTimeout(OCRError):
    """Tesseract couldn't finish a page in time — in practice a page so
    noisy or degraded that the engine thrashes. Treated like an
    unreadable scan (low confidence), not like a crashed file."""


class OCRUnavailable(OCRError):
    """The OCR engine itself isn't usable on this machine (Tesseract or
    poppler not installed / not on PATH). Distinct from OCRError so the
    caller can say "OCR isn't set up" rather than "this file is bad"."""


@dataclass(frozen=True)
class OCRWord:
    """One recognised word and where it sits in OCRResult.text.

    start/end are character offsets into the final text, so anything
    found in the text later (a date, a section number) can be traced
    back to the exact words — and therefore the exact confidences — it
    was read from. That is what makes per-FIELD confidence possible.
    """

    start: int
    end: int
    confidence: float
    page: int


@dataclass(frozen=True)
class OCRResult:
    text: str
    # Mean per-word confidence on a 0-100 scale, over words the engine
    # actually recognised. None when no words were found at all.
    confidence: float | None
    pages_processed: int
    # True when the PDF had more pages than OCR_MAX_PAGES, so only the
    # first pages were read. The text is then incomplete by design.
    truncated: bool
    word_count: int
    words: tuple[OCRWord, ...] = ()


class OCRProvider(ABC):
    name: str

    @abstractmethod
    def ocr_pdf(self, data: bytes) -> OCRResult:
        """Rasterise and OCR a scanned PDF. Blocking and CPU-heavy —
        call from a worker thread, never directly on the event loop."""
