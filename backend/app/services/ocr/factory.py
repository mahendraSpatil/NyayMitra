from ...config import settings
from .base import OCRProvider

_provider: OCRProvider | None = None


def get_ocr_provider() -> OCRProvider | None:
    """None when OCR_PROVIDER=none — scans then stay `no_text_layer`,
    exactly as before OCR existed. Chosen once per process, like
    app/llm/factory.py; no per-request switching."""
    global _provider
    name = settings.ocr_provider.lower()
    if name == "none":
        return None
    if _provider is None:
        if name == "tesseract":
            from .tesseract import TesseractProvider

            _provider = TesseractProvider()
        else:
            raise RuntimeError(f"Unknown OCR_PROVIDER {settings.ocr_provider!r}")
    return _provider
