"""Fixtures for tests that exercise the real live Firebase project — same
convention used throughout this project's manual verification passes,
kept here as a real, re-runnable suite instead of a one-off script.
Requires GOOGLE_APPLICATION_CREDENTIALS (for the Admin SDK) and
FIREBASE_WEB_API_KEY (backend/.env) to be set, and the three seeded test
accounts (backend/scripts/seed.py) to exist.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth import get_firestore_db
from app.config import settings
from app.main import app

_TEST_ACCOUNTS = {
    "advocate": "advocate@nyaymitra.test",
    "ngo": "ngo@nyaymitra.test",
    "family": "family@nyaymitra.test",
}
_PASSWORD = "NyayMitra@Dev1"


@pytest.fixture(scope="session")
def db():
    return get_firestore_db()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def accounts():
    """{'advocate': {'uid': ..., 'token': ...}, 'ngo': ..., 'family': ...}
    — one real, signed-in identity per seeded role, reused across the
    whole test session rather than re-authenticating per test.
    """
    if not settings.firebase_web_api_key:
        pytest.skip("FIREBASE_WEB_API_KEY not set in backend/.env")

    result = {}
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={settings.firebase_web_api_key}"
    )
    with httpx.Client(timeout=10) as http_client:
        for role, email in _TEST_ACCOUNTS.items():
            response = http_client.post(
                url, json={"email": email, "password": _PASSWORD, "returnSecureToken": True}
            )
            response.raise_for_status()
            data = response.json()
            result[role] = {"uid": data["localId"], "token": data["idToken"]}
    return result


@pytest.fixture
def auth_headers(accounts):
    def _headers(role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {accounts[role]['token']}"}

    return _headers


@pytest.fixture
def make_case(db):
    """Creates a case doc directly via the Admin SDK (not through the API
    — these tests are about invite/hearing authorization, not case
    creation, which commit 2's tests already cover) and deletes it, its
    hearings, and any invites/inviteAttempts referencing it afterward.
    """
    created_ids: list[str] = []

    def _make(**fields):
        ref = db.collection("cases").document()
        base = {
            "undertrialName": "Test Case",
            "firNumber": "",
            "court": "",
            "advocateUid": None,
            "advocateName": "",
            "familyUids": [],
            "ngoUids": [],
            "createdBy": "",
            "ownerType": "advocate",
            "stage": "intake",
            "stageLabel": "Case Intake",
            "stageTone": "info",
            "nextHearingDate": None,
            "documentCount": 0,
            "timeline": [],
        }
        base.update(fields)
        ref.set(base)
        created_ids.append(ref.id)
        return ref.id

    yield _make

    for case_id in created_ids:
        case_ref = db.collection("cases").document(case_id)
        for hearing in case_ref.collection("hearings").stream():
            hearing.reference.delete()
        for invite in db.collection("invites").where("caseId", "==", case_id).stream():
            invite.reference.delete()
        for attempt in db.collection("inviteAttempts").where("caseId", "==", case_id).stream():
            attempt.reference.delete()
        case_ref.delete()
