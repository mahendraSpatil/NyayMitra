"""Key-field review API + what /chat shows the model — real Postgres,
real auth, fake LLM (same pattern as test_chat.py).

Run with: pytest tests/v2/test_document_fields.py -v
"""

import uuid
from datetime import date

import pytest

from app.db.models import CaseMember, Document, DocumentField
from app.llm.base import LLMProvider, LLMResult
from app.llm.factory import get_llm
from app.main import app
from app.services.pdf_extraction import ExtractionResult
from app.services.ocr.base import OCRWord
from app.services.v2.document_fields import add_fields_for_document

OCR_TEXT = "FIR No. 214/2026\n\nAccused arrested on 14/03/2026 under Section 379 IPC."


class _FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self):
        self.calls = []
        self.reply = "ok"

    async def generate(self, messages, *, max_tokens=400, temperature=0.2) -> LLMResult:
        self.calls.append(messages)
        return LLMResult(text=self.reply, model="fake:test", latency_ms=1)

    async def health(self) -> bool:
        return True


@pytest.fixture
def fake_llm():
    provider = _FakeProvider()
    app.dependency_overrides[get_llm] = lambda: provider
    yield provider
    del app.dependency_overrides[get_llm]


@pytest.fixture
def scanned_case(make_case, accounts, db):
    """Advocate (manager) + family (joined by invite, NOT a manager) on a
    case with one OCR'd FIR whose fields all need review."""
    case_id = make_case(created_by=accounts["advocate"]["uid"], owner_type="advocate")
    db.add(CaseMember(case_id=case_id, user_id=accounts["advocate"]["uid"], role="advocate", is_manager=True))
    db.add(CaseMember(case_id=case_id, user_id=accounts["family"]["uid"], role="family", is_manager=False))
    doc = Document(
        id=uuid.uuid4(), case_id=case_id, doc_type="fir", storage_path=f"cases/test/{uuid.uuid4()}.pdf",
        uploaded_by=accounts["advocate"]["uid"], ocr_status="ocr_extracted", raw_text=OCR_TEXT,
        text_source="ocr", ocr_confidence=92.0, statutes=[],
    )
    db.add(doc)
    db.flush()
    import re

    words = tuple(OCRWord(m.start(), m.end(), 93.0, 1) for m in re.finditer(r"\S+", OCR_TEXT))
    add_fields_for_document(
        db, doc,
        ExtractionResult(OCR_TEXT, "ocr_extracted", "ocr", 92.0, words=words),
        reference_date=date(2026, 10, 26),
    )
    db.commit()
    return case_id, doc.id


def _fields(client, auth_headers, case_id, role="advocate", **params):
    r = client.get(f"/api/v2/cases/{case_id}/document-fields", params=params, headers=auth_headers(role))
    assert r.status_code == 200, r.text
    return r.json()


def test_ocr_fields_are_listed_as_needing_review(client, auth_headers, scanned_case):
    case_id, doc_id = scanned_case
    fields = _fields(client, auth_headers, case_id, status="needs_review")
    assert sorted((f["kind"], f["value"]) for f in fields) == [
        ("date", "2026-03-14"), ("fir_number", "214/2026"), ("section", "379 IPC"),
    ]
    assert all(f["confidence"] == 93.0 and f["source"] == "ocr" for f in fields)


def test_fields_appear_on_the_document_list(client, auth_headers, scanned_case):
    case_id, doc_id = scanned_case
    docs = client.get(f"/api/v2/cases/{case_id}/documents", headers=auth_headers("family")).json()
    assert len(docs[0]["fields"]) == 3


def test_non_member_cannot_list_fields(client, auth_headers, make_case, accounts):
    case_id = make_case(created_by=accounts["advocate"]["uid"])
    r = client.get(f"/api/v2/cases/{case_id}/document-fields", headers=auth_headers("ngo"))
    assert r.status_code == 403


def test_invited_family_member_can_see_but_not_confirm(client, auth_headers, scanned_case):
    case_id, _ = scanned_case
    field = _fields(client, auth_headers, case_id, role="family")[0]
    r = client.post(
        f"/api/v2/cases/{case_id}/document-fields/{field['id']}/confirm", json={}, headers=auth_headers("family")
    )
    assert r.status_code == 403


def test_advocate_confirms_with_a_correction_and_the_original_is_kept(client, auth_headers, scanned_case, db):
    case_id, _ = scanned_case
    date_field = [f for f in _fields(client, auth_headers, case_id) if f["kind"] == "date"][0]
    r = client.post(
        f"/api/v2/cases/{case_id}/document-fields/{date_field['id']}/confirm",
        json={"value": "15/03/2026"},
        headers=auth_headers("advocate"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["value"] == "2026-03-15"
    assert body["extractedValue"] == "2026-03-14"  # what OCR read stays auditable
    assert body["reviewedRole"] == "advocate"


def test_invalid_correction_is_refused(client, auth_headers, scanned_case):
    case_id, _ = scanned_case
    date_field = [f for f in _fields(client, auth_headers, case_id) if f["kind"] == "date"][0]
    r = client.post(
        f"/api/v2/cases/{case_id}/document-fields/{date_field['id']}/confirm",
        json={"value": "31/02/2026"},
        headers=auth_headers("advocate"),
    )
    assert r.status_code == 422
    assert _fields(client, auth_headers, case_id, status="needs_review")  # unchanged


def test_field_from_another_case_is_404(client, auth_headers, scanned_case, make_case, accounts, db):
    case_id, _ = scanned_case
    field_id = _fields(client, auth_headers, case_id)[0]["id"]
    other = make_case(created_by=accounts["advocate"]["uid"])
    db.add(CaseMember(case_id=other, user_id=accounts["advocate"]["uid"], role="advocate", is_manager=True))
    db.commit()
    r = client.post(
        f"/api/v2/cases/{other}/document-fields/{field_id}/confirm", json={}, headers=auth_headers("advocate")
    )
    assert r.status_code == 404


def test_chat_never_sees_unconfirmed_values_then_sees_confirmed_ones(
    client, auth_headers, scanned_case, fake_llm
):
    case_id, _ = scanned_case

    r = client.post("/api/v2/chat", json={"message": "When was he arrested?", "caseId": str(case_id)},
                    headers=auth_headers("advocate"))
    assert r.status_code == 200, r.text
    assert r.json()["fieldsPendingReview"] == 3
    prompt = fake_llm.calls[-1][-1]["content"]
    assert "14/03/2026" not in prompt and "214/2026" not in prompt
    assert "[arrest date unclear, not yet confirmed]" in prompt
    assert "not confirmed yet" in prompt

    date_field = [f for f in _fields(client, auth_headers, case_id) if f["kind"] == "date"][0]
    client.post(
        f"/api/v2/cases/{case_id}/document-fields/{date_field['id']}/confirm",
        json={"value": "15/03/2026"},
        headers=auth_headers("advocate"),
    )

    r = client.post("/api/v2/chat", json={"message": "When was he arrested?", "caseId": str(case_id)},
                    headers=auth_headers("advocate"))
    assert r.json()["fieldsPendingReview"] == 2
    prompt = fake_llm.calls[-1][-1]["content"]
    assert "arrested on 15 March 2026" in prompt  # the reviewer's correction, not OCR's reading
    assert "confirmed by advocate" in prompt


def test_rejected_field_stays_hidden_and_stops_counting_as_pending(
    client, auth_headers, scanned_case, fake_llm
):
    case_id, _ = scanned_case
    section = [f for f in _fields(client, auth_headers, case_id) if f["kind"] == "section"][0]
    r = client.post(
        f"/api/v2/cases/{case_id}/document-fields/{section['id']}/reject", headers=auth_headers("advocate")
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"

    r = client.post("/api/v2/chat", json={"message": "Which section?", "caseId": str(case_id)},
                    headers=auth_headers("advocate"))
    assert r.json()["fieldsPendingReview"] == 2
    assert "Section [unclear] IPC" in fake_llm.calls[-1][-1]["content"]


# ---- missing facts, adding by hand, asking the model -----------------------

def _doc(client, auth_headers, case_id, role="advocate"):
    docs = client.get(f"/api/v2/cases/{case_id}/documents", headers=auth_headers(role)).json()
    return docs[0]


def test_missing_required_facts_are_reported_on_the_document(client, auth_headers, scanned_case):
    case_id, _ = scanned_case
    doc = _doc(client, auth_headers, case_id)
    # The FIR text has a number, a section and an arrest date — but no
    # registration date.
    assert [(m["kind"], m["role"], m["label"]) for m in doc["missingFacts"]] == [
        ("date", "fir_registered", "FIR registration date")
    ]


def test_reviewer_adds_a_missing_fact_and_it_reaches_the_model(
    client, auth_headers, scanned_case, fake_llm
):
    case_id, doc_id = scanned_case
    r = client.post(
        f"/api/v2/cases/{case_id}/documents/{doc_id}/fields",
        json={"kind": "date", "role": "fir_registered", "value": "12/03/2026"},
        headers=auth_headers("advocate"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["status"], body["extractor"], body["source"], body["rawText"]) == (
        "confirmed", "manual", "manual", None
    )
    assert _doc(client, auth_headers, case_id)["missingFacts"] == []

    client.post("/api/v2/chat", json={"message": "When was the FIR filed?", "caseId": str(case_id)},
                headers=auth_headers("advocate"))
    prompt = fake_llm.calls[-1][-1]["content"]
    assert "12 March 2026" in prompt and "added by advocate from the original" in prompt


def test_invited_family_cannot_add_facts(client, auth_headers, scanned_case):
    case_id, doc_id = scanned_case
    r = client.post(
        f"/api/v2/cases/{case_id}/documents/{doc_id}/fields",
        json={"kind": "date", "role": "arrest", "value": "12/03/2026"},
        headers=auth_headers("family"),
    )
    assert r.status_code == 403


def test_bad_manual_fact_is_refused(client, auth_headers, scanned_case):
    case_id, doc_id = scanned_case
    for payload in (
        {"kind": "date", "role": "arrest", "value": "31/02/2026"},
        {"kind": "section", "role": "arrest", "value": "379 IPC"},
        {"kind": "colour", "value": "blue"},
    ):
        r = client.post(f"/api/v2/cases/{case_id}/documents/{doc_id}/fields", json=payload,
                        headers=auth_headers("advocate"))
        assert r.status_code == 422, payload


def test_chat_is_told_which_key_facts_are_not_in_the_documents(
    client, auth_headers, scanned_case, fake_llm
):
    case_id, _ = scanned_case
    client.post("/api/v2/chat", json={"message": "When is the next hearing?", "caseId": str(case_id)},
                headers=auth_headers("advocate"))
    prompt = fake_llm.calls[-1][-1]["content"]
    assert "hearing date" in prompt and "not found in the uploaded documents" in prompt


def test_find_facts_keeps_only_grounded_suggestions_and_they_need_review(
    client, auth_headers, make_case, accounts, db, fake_llm
):
    case_id = make_case(created_by=accounts["advocate"]["uid"])
    db.add(CaseMember(case_id=case_id, user_id=accounts["advocate"]["uid"], role="advocate", is_manager=True))
    text = "Matter called out. Accused present. The matter shall now come up on 22.07.2026 before this court."
    doc = Document(
        id=uuid.uuid4(), case_id=case_id, doc_type="remand_order", storage_path=f"cases/test/{uuid.uuid4()}.pdf",
        uploaded_by=accounts["advocate"]["uid"], ocr_status="extracted", raw_text=text,
        text_source="text_layer", statutes=[],
    )
    db.add(doc)
    db.commit()
    fake_llm.reply = (
        '[{"kind": "date", "role": "hearing", "quote": "shall now come up on 22.07.2026"},'
        ' {"kind": "date", "role": "arrest", "quote": "arrested on 01.03.2026"}]'
    )
    r = client.post(f"/api/v2/cases/{case_id}/documents/{doc.id}/find-facts", headers=auth_headers("advocate"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["suggested"], body["dropped"]) == (2, 1)
    (added,) = body["added"]
    assert (added["value"], added["role"], added["extractor"], added["status"]) == (
        "2026-07-22", "hearing", "llm", "needs_review"
    )


def test_find_facts_503_when_model_is_down(client, auth_headers, scanned_case):
    from app.llm.base import LLMUnavailable

    class _Down(_FakeProvider):
        async def generate(self, messages, *, max_tokens=400, temperature=0.2):
            raise LLMUnavailable("down")

    app.dependency_overrides[get_llm] = lambda: _Down()
    try:
        case_id, doc_id = scanned_case
        r = client.post(f"/api/v2/cases/{case_id}/documents/{doc_id}/find-facts", headers=auth_headers("advocate"))
        assert r.status_code == 503
    finally:
        del app.dependency_overrides[get_llm]


def test_confirming_a_date_records_that_a_person_set_its_role(client, auth_headers, scanned_case):
    case_id, _ = scanned_case
    date_field = [f for f in _fields(client, auth_headers, case_id) if f["kind"] == "date"][0]
    r = client.post(
        f"/api/v2/cases/{case_id}/document-fields/{date_field['id']}/confirm",
        json={"role": "arrest"}, headers=auth_headers("advocate"),
    )
    assert r.json()["roleBasis"] == "reviewer"
