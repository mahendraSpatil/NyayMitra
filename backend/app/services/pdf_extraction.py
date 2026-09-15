"""Text extraction for typed PDFs only — no OCR for scans yet. A PDF with
no real text layer (a scanned image with no embedded text) extracts to
nothing; that's reported as its own status rather than silently stored as
an empty rawText, so the UI can tell a family "we can't read this scan
yet" instead of pretending the upload just has no content.
"""

from io import BytesIO

from pypdf import PdfReader

# Matches the three states the /documents endpoints and the Flutter upload
# sheet both branch on. Not an enum in Firestore (the schema just says
# ocrStatus, no fixed values were ever defined) - these are this backend's
# concrete choices for it.
STATUS_EXTRACTED = "extracted"
STATUS_NO_TEXT_LAYER = "no_text_layer"
STATUS_FAILED = "failed"


def extract_text(data: bytes) -> tuple[str | None, str]:
    try:
        reader = PdfReader(BytesIO(data))
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return None, STATUS_FAILED

    text = "\n".join(pages_text).strip()
    if not text:
        return None, STATUS_NO_TEXT_LAYER
    return text, STATUS_EXTRACTED
