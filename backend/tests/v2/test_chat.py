"""POST /api/v2/chat and the extended GET /health — real Postgres, real
auth, but a fake LLMProvider swapped in via FastAPI's own
dependency-override mechanism (app.dependency_overrides[get_llm] = ...),
the same way this suite could override get_db/get_current_user if it
ever needed to. No real llama-server required to run this file.

Run with: pytest tests/v2/test_chat.py -v
"""

import uuid

import pytest

from app.db.models import CaseMember, Document
from app.llm.base import LLMProvider, LLMResult, LLMUnavailable
from app.llm.factory import get_llm
from app.main import app


class _FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, *, text: str = "This is a test reply.", raise_unavailable: bool = False):
        self.text = text
        self.raise_unavailable = raise_unavailable
        self.calls: list[list[dict]] = []

    async def generate(self, messages, *, max_tokens=400, temperature=0.2) -> LLMResult:
        self.calls.append(messages)
        if self.raise_unavailable:
            raise LLMUnavailable("fake provider is down")
        return LLMResult(text=self.text, model="fake:test", latency_ms=1)

    async def health(self) -> bool:
        return not self.raise_unavailable


@pytest.fixture
def fake_llm():
    provider = _FakeProvider()
    app.dependency_overrides[get_llm] = lambda: provider
    yield provider
    del app.dependency_overrides[get_llm]


def _advocate_owned_case(make_case, accounts, db):
    case_id = make_case(created_by=accounts["advocate"]["uid"], owner_type="advocate")
    db.add(CaseMember(case_id=case_id, user_id=accounts["advocate"]["uid"], role="advocate", is_manager=True))
    db.commit()
    return case_id


def test_chat_requires_auth(client, fake_llm):
    response = client.post("/api/v2/chat", json={"message": "hello"})
    assert response.status_code == 401
    assert fake_llm.calls == []


def test_chat_403_for_non_member_case_never_reaches_the_model(
    client, auth_headers, make_case, accounts, fake_llm, db
):
    case_id = _advocate_owned_case(make_case, accounts, db)
    response = client.post(
        "/api/v2/chat",
        json={"message": "hello", "caseId": str(case_id)},
        headers=auth_headers("family"),
    )
    assert response.status_code == 403
    assert fake_llm.calls == []


def test_chat_without_a_case_still_answers(client, auth_headers, fake_llm):
    response = client.post(
        "/api/v2/chat", json={"message": "What is bail?"}, headers=auth_headers("advocate")
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "This is a test reply."
    assert body["modelUsed"] == "fake:test"
    assert body["latencyMs"] == 1
    assert body["citedDocuments"] == []
    # No case in scope — CASE DETAILS in the prompt must be empty, not
    # fabricated.
    assert "CASE DETAILS:\n{}" in fake_llm.calls[0][-1]["content"]


def test_chat_verification_status_is_always_unverified_even_with_a_citation(
    client, auth_headers, fake_llm
):
    fake_llm.text = "You may want to review Section 436A CrPC about bail."
    response = client.post(
        "/api/v2/chat", json={"message": "what about bail?"}, headers=auth_headers("advocate")
    )
    assert response.status_code == 200
    body = response.json()
    # Extracted, real: the model's own text really did cite this.
    assert "Section 436A CRPC" in body["citedSections"]
    # Never flips to verified just because a citation was found — no
    # document_faithfulness classifier exists to earn that (verify_draft's
    # own docstring).
    assert body["verificationStatus"] == "unverified"


def test_chat_503_when_llm_unavailable_no_fallback(client, auth_headers):
    provider = _FakeProvider(raise_unavailable=True)
    app.dependency_overrides[get_llm] = lambda: provider
    try:
        response = client.post(
            "/api/v2/chat", json={"message": "hello"}, headers=auth_headers("advocate")
        )
        assert response.status_code == 503
        assert len(provider.calls) == 1  # tried exactly once, never retried onto a different provider
    finally:
        del app.dependency_overrides[get_llm]


def test_chat_includes_real_case_details_and_document_context(
    client, auth_headers, make_case, accounts, fake_llm, db
):
    case_id = make_case(
        created_by=accounts["advocate"]["uid"],
        owner_type="advocate",
        undertrial_name="Test Chat Person",
        fir_number="CHAT-1",
    )
    db.add(CaseMember(case_id=case_id, user_id=accounts["advocate"]["uid"], role="advocate", is_manager=True))
    document_id = uuid.uuid4()
    db.add(
        Document(
            id=document_id,
            case_id=case_id,
            doc_type="fir",
            storage_path="cases/test/doc.pdf",
            uploaded_by=accounts["advocate"]["uid"],
            ocr_status="extracted",
            raw_text="The undertrial was arrested under Section 302 IPC.",
            text_source="text_layer",
            statutes=[],
        )
    )
    db.commit()

    try:
        response = client.post(
            "/api/v2/chat",
            json={"message": "What section was cited?", "caseId": str(case_id)},
            headers=auth_headers("advocate"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["citedDocuments"] == [
            {
                "docId": str(document_id),
                "docType": "fir",
                "textSource": "text_layer",
                "ocrConfidence": None,
            }
        ]
        assert body["skippedDocuments"] == []

        prompt = fake_llm.calls[0][-1]["content"]
        assert "Test Chat Person" in prompt  # real Case column, not a fabricated field
        assert "arrested under Section 302 IPC" in prompt  # real document excerpt
    finally:
        db.query(Document).filter(Document.id == document_id).delete()
        db.commit()


def _add_doc(db, case_id, uploader, *, text, ocr_status, text_source, confidence=None, doc_type="fir"):
    doc = Document(
        id=uuid.uuid4(),
        case_id=case_id,
        doc_type=doc_type,
        storage_path=f"cases/test/{uuid.uuid4()}.pdf",
        uploaded_by=uploader,
        ocr_status=ocr_status,
        raw_text=text,
        text_source=text_source,
        ocr_confidence=confidence,
        statutes=[],
    )
    db.add(doc)
    db.commit()
    return doc


def test_chat_low_confidence_scan_is_kept_out_of_the_prompt_and_reported(
    client, auth_headers, make_case, accounts, fake_llm, db
):
    """The point of OCR gating: a scan we are not confident in must never
    reach the model, and the user must be told it was skipped rather than
    getting an answer that silently ignores their document."""
    case_id = _advocate_owned_case(make_case, accounts, db)
    uploader = accounts["advocate"]["uid"]
    bad = _add_doc(
        db, case_id, uploader,
        text="Sectlon 4З7 CrPC arrestd on l4 Marcb",  # garbled OCR
        ocr_status="ocr_low_confidence", text_source="ocr", confidence=41.0,
    )
    try:
        response = client.post(
            "/api/v2/chat",
            json={"message": "What section?", "caseId": str(case_id)},
            headers=auth_headers("advocate"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["citedDocuments"] == []
        assert body["skippedDocuments"] == [
            {
                "docId": str(bad.id),
                "docType": "fir",
                "reason": "low_ocr_confidence",
                "ocrConfidence": 41.0,
            }
        ]
        assert "Sectlon" not in fake_llm.calls[0][-1]["content"]
    finally:
        db.query(Document).filter(Document.case_id == case_id).delete()
        db.commit()


def test_chat_good_scan_is_used_labelled_as_ocr_and_flagged_in_the_prompt(
    client, auth_headers, make_case, accounts, fake_llm, db
):
    case_id = _advocate_owned_case(make_case, accounts, db)
    scan = _add_doc(
        db, case_id, accounts["advocate"]["uid"],
        text="Accused arrested under Section 379 IPC.",
        ocr_status="ocr_extracted", text_source="ocr", confidence=93.2,
    )
    try:
        response = client.post(
            "/api/v2/chat",
            json={"message": "What section?", "caseId": str(case_id)},
            headers=auth_headers("advocate"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["citedDocuments"] == [
            {"docId": str(scan.id), "docType": "fir", "textSource": "ocr", "ocrConfidence": 93.2}
        ]
        prompt = fake_llm.calls[0][-1]["content"]
        assert "scanned copy, read by OCR" in prompt
        assert "may contain misread characters" in prompt
        assert "Section 379 IPC" in prompt
    finally:
        db.query(Document).filter(Document.case_id == case_id).delete()
        db.commit()


def test_health_reports_llm_status(client, fake_llm):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm"] is True
    assert body["llmProvider"] == "fake"
