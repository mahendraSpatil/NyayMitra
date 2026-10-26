"""OCR layer — no database, no network.

Pure/mocked tests always run. The real-engine tests need the Tesseract and
poppler binaries (README.md's OCR section) and are skipped, not failed,
when those aren't installed.

Run with: pytest tests/test_ocr.py -v
"""

import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import settings
from app.services import pdf_extraction
from app.services.ocr.base import OCRError, OCRResult, OCRTimeout, OCRUnavailable
from app.services.ocr.tesseract import _page_from_data
from app.services.pdf_extraction import extract_document

HAVE_BINARIES = bool(shutil.which("tesseract") and (shutil.which("pdftoppm") or settings.poppler_path))
needs_engine = pytest.mark.skipif(not HAVE_BINARIES, reason="tesseract/poppler not installed")


# ---- pure: reconstructing text + confidence from image_to_data ----------

def _data(rows):
    """rows: (text, conf, block, par, line)"""
    return {
        "text": [r[0] for r in rows],
        "conf": [r[1] for r in rows],
        "block_num": [r[2] for r in rows],
        "par_num": [r[3] for r in rows],
        "line_num": [r[4] for r in rows],
    }


def test_layout_rows_with_conf_minus_one_are_ignored_not_averaged_in():
    text, spans = _page_from_data(
        _data([("", "-1", 1, 0, 0), ("Section", "96", 1, 1, 1), ("379", "90", 1, 1, 1), ("", "-1", 1, 1, 1)])
    )
    assert text == "Section 379"
    assert [c for _, _, c in spans] == [96.0, 90.0]


def test_word_spans_point_at_the_words_in_the_rebuilt_text():
    text, spans = _page_from_data(
        _data([("First", "91", 1, 1, 1), ("line", "92", 1, 1, 1), ("14/03/2026", "55", 1, 1, 2),
               ("New", "93", 2, 1, 1), ("para", "94", 2, 1, 1)])
    )
    assert [text[s:e] for s, e, _ in spans] == ["First", "line", "14/03/2026", "New", "para"]
    assert spans[2][2] == 55.0


def test_paragraphs_survive_as_blank_line_separated_blocks():
    # select_excerpt() splits on blank lines — flattening paragraphs would
    # turn the whole page into one un-rankable blob.
    text, _ = _page_from_data(
        _data([("First", "90", 1, 1, 1), ("line", "90", 1, 1, 1), ("Second", "90", 1, 1, 2),
               ("New", "90", 2, 1, 1), ("para", "90", 2, 1, 1)])
    )
    assert text == "First line\nSecond\n\nNew para"


def test_whitespace_only_tokens_are_not_words():
    text, spans = _page_from_data(_data([("  ", "95", 1, 1, 1), ("Word", "80", 1, 1, 1)]))
    assert text == "Word" and [c for _, _, c in spans] == [80.0]


# ---- status mapping, with a fake provider (no binaries needed) ----------

def _blank_pdf() -> bytes:
    buf = io.BytesIO()
    Image.new("L", (200, 200), 255).save(buf, "PDF")
    return buf.getvalue()


class _Fake:
    name = "fake"

    def __init__(self, result=None, raises=None):
        self.result, self.raises = result, raises

    def ocr_pdf(self, data):
        if self.raises:
            raise self.raises
        return self.result


def _with_provider(monkeypatch, provider):
    monkeypatch.setattr(pdf_extraction, "get_ocr_provider", lambda: provider)


def test_confident_scan_is_ocr_extracted(monkeypatch):
    _with_provider(monkeypatch, _Fake(OCRResult("Section 379", 91.0, 1, False, 2)))
    r = extract_document(_blank_pdf())
    assert (r.status, r.text_source, r.confidence) == ("ocr_extracted", "ocr", 91.0)
    assert r.text == "Section 379"


def test_scan_below_threshold_is_low_confidence_but_text_is_kept_for_humans(monkeypatch):
    monkeypatch.setattr(settings, "ocr_min_confidence", 60.0)
    _with_provider(monkeypatch, _Fake(OCRResult("Sectlon 4З7", 59.9, 1, False, 2)))
    r = extract_document(_blank_pdf())
    assert r.status == "ocr_low_confidence"
    assert r.text == "Sectlon 4З7"


def test_threshold_is_inclusive_and_configurable(monkeypatch):
    monkeypatch.setattr(settings, "ocr_min_confidence", 75.0)
    _with_provider(monkeypatch, _Fake(OCRResult("x", 75.0, 1, False, 1)))
    assert extract_document(_blank_pdf()).status == "ocr_extracted"
    monkeypatch.setattr(settings, "ocr_min_confidence", 75.1)
    assert extract_document(_blank_pdf()).status == "ocr_low_confidence"


def test_no_words_recognised_is_low_confidence_with_no_text(monkeypatch):
    _with_provider(monkeypatch, _Fake(OCRResult("", None, 1, False, 0)))
    r = extract_document(_blank_pdf())
    assert (r.status, r.text, r.confidence) == ("ocr_low_confidence", None, 0.0)


def test_ocr_timeout_is_an_unreadable_scan_not_a_failure(monkeypatch):
    _with_provider(monkeypatch, _Fake(raises=OCRTimeout("page 1 timed out")))
    r = extract_document(_blank_pdf())
    assert r.status == "ocr_low_confidence" and r.text is None


def test_missing_binaries_leave_the_scan_as_no_text_layer(monkeypatch):
    _with_provider(monkeypatch, _Fake(raises=OCRUnavailable("tesseract not found")))
    assert extract_document(_blank_pdf()).status == "no_text_layer"


def test_ocr_crash_is_failed(monkeypatch):
    _with_provider(monkeypatch, _Fake(raises=OCRError("boom")))
    assert extract_document(_blank_pdf()).status == "failed"


def test_ocr_disabled_keeps_old_behaviour(monkeypatch):
    _with_provider(monkeypatch, None)
    r = extract_document(_blank_pdf())
    assert (r.status, r.text_source) == ("no_text_layer", "none")


def test_truncated_scan_carries_a_marker_in_its_text(monkeypatch):
    _with_provider(monkeypatch, _Fake(OCRResult("Page one text.", 90.0, 20, True, 3)))
    r = extract_document(_blank_pdf())
    assert "only the first 20 pages were read" in r.text
    assert r.truncated is True


def test_not_a_pdf_is_failed():
    assert extract_document(b"definitely not a pdf").status == "failed"


# ---- real engine ---------------------------------------------------------

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",  # Linux
    "C:/Windows/Fonts/times.ttf",  # Windows
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",  # macOS
]
_LINES = [
    "FIRST INFORMATION REPORT (FIR) No. 214/2026",
    "Under Section 379 of the Indian Penal Code",
    "The accused was arrested on 14 March 2026.",
]


def _scan_pdf(*, blur=0, noise=0.0, rot=0, scale=1.0) -> bytes:
    font = None
    for candidate in _FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(candidate, 56)
            break
        except OSError:
            continue
    if font is None:
        pytest.skip("no TrueType font found to render a test scan")
    img = Image.new("L", (2480, 3508), 255)
    draw = ImageDraw.Draw(img)
    y = 300
    for line in _LINES:
        draw.text((250, y), line, font=font, fill=0)
        y += 110
    if rot:
        img = img.rotate(rot, fillcolor=255)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        import random

        random.seed(1)
        px = img.load()
        for _ in range(int(img.width * img.height * noise)):
            px[random.randrange(img.width), random.randrange(img.height)] = random.choice((0, 255))
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=300 * scale)
    return buf.getvalue()


@needs_engine
def test_real_clean_scan_is_read_correctly_with_high_confidence():
    r = extract_document(_scan_pdf())
    assert r.status == "ocr_extracted"
    assert r.text_source == "ocr"
    assert r.confidence >= 85
    assert "Section 379" in r.text and "14 March 2026" in r.text


@needs_engine
def test_real_scan_word_spans_line_up_with_the_text():
    r = extract_document(_scan_pdf())
    assert r.words, "OCR should return word spans"
    for w in r.words:
        assert r.text[w.start:w.end].strip() == r.text[w.start:w.end]
        assert r.text[w.start:w.end]
    assert any(r.text[w.start:w.end] == "379" for w in r.words)


@needs_engine
def test_real_degraded_scan_is_not_trusted():
    """A third-generation-photocopy stand-in: blurry, speckled, tilted,
    low resolution. Whatever the engine reads, it must NOT come back as
    ocr_extracted — confident-looking garbage is the failure this whole
    gate exists to prevent."""
    r = extract_document(_scan_pdf(blur=4, noise=0.02, rot=3, scale=0.5))
    assert r.status == "ocr_low_confidence", (r.status, r.confidence, r.text)
