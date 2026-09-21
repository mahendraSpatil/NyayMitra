"""Fixtures for the /api/v2 (Postgres/JWT) test suite — the replacement
for tests/conftest.py's Firebase-based fixtures, which sign in against
Identity Toolkit (now deliberately blocked for non-browser callers, see
NyayMitra.md). Everything here talks to the real local Postgres and the
real /api/v2 endpoints through a single in-process TestClient — no
external service, no restricted API key.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import Case, CaseMember, InviteAttempt, User
from app.main import app

_PASSWORD = "NyayMitra@Dev1"
_EMAILS = {
    "advocate": "advocate@nyaymitra.test",
    "ngo": "ngo@nyaymitra.test",
    "family": "family@nyaymitra.test",
}


@pytest.fixture(scope="session")
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def accounts(client, db):
    """{'advocate': {'uid': ..., 'token': ...}, 'ngo': ..., 'family': ...}
    — one real, logged-in identity per seeded role (backend/scripts/seed_pg.py),
    obtained through the real /api/v2/auth/login endpoint rather than any
    Firebase-adjacent shortcut.
    """
    result = {}
    for role, email in _EMAILS.items():
        response = client.post("/api/v2/auth/login", json={"email": email, "password": _PASSWORD})
        response.raise_for_status()
        token = response.json()["accessToken"]
        user_id = db.scalar(select(User.id).where(User.email == email))
        result[role] = {"uid": user_id, "access_token": token}
    return result


@pytest.fixture
def auth_headers(accounts):
    def _headers(role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {accounts[role]['access_token']}"}

    return _headers


@pytest.fixture
def make_case(db):
    """Creates a case row directly against Postgres (not through the API
    — these tests are about invite/authorization behavior, not case
    creation, which has its own coverage) and deletes it — and, since
    invite_attempts.case_id is ON DELETE SET NULL rather than CASCADE,
    any attempt logs that reference it too — afterward. Commits
    immediately: the running app handles each HTTP request on its own
    session/connection, so a fixture write has to actually land in
    Postgres, not just this fixture's local uncommitted transaction, to
    be visible to it.
    """
    created_ids: list[uuid.UUID] = []

    def _make(**fields):
        defaults = dict(
            undertrial_name="Test Case",
            fir_number="",
            court="",
            owner_type="advocate",
            stage="intake",
            stage_label="Case Intake",
            stage_tone="info",
            document_count=0,
        )
        defaults.update(fields)
        case = Case(**defaults)
        db.add(case)
        db.commit()
        created_ids.append(case.id)
        return case.id

    yield _make

    for case_id in created_ids:
        db.query(CaseMember).filter(CaseMember.case_id == case_id).delete()
        db.query(InviteAttempt).filter(InviteAttempt.case_id == case_id).delete()
        case = db.get(Case, case_id)
        if case is not None:
            db.delete(case)  # cascades: hearings, documents, invites
        db.commit()
