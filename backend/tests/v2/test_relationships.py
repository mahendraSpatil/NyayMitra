"""End-to-end proof of the whole multi-user relationship story — not one
relationship at a time (test_invites.py) and not against the three seeded
accounts (conftest.py's `accounts` fixture), but against accounts created
through the real POST /auth/register + POST /auth/login endpoints, the
same path a real new user takes.

Run with: pytest tests/v2/test_relationships.py -v
"""

import time
import uuid

import pytest
from sqlalchemy import select

from app.db.models import Case, CaseMember, InviteAttempt, User

_PASSWORD = "NyayMitra-Rel-Test-2026"  # >= 12 chars, not on the password deny-list


@pytest.fixture
def people(client, db):
    """Registers, then signs in, one fresh account per role — proving
    register -> login end-to-end as a side effect, and exercising the
    exact two-step flow the Flutter client now requires (register no
    longer issues a session, see routers/auth.py's register()).
    """
    created = {}
    for key, role in [
        ("advocate", "advocate"),
        ("ngo", "ngo"),
        ("family_a", "family"),
        ("family_b", "family"),
    ]:
        email = f"reltest-{key}-{uuid.uuid4().hex[:8]}@nyaymitra.test"
        register = client.post(
            "/api/v2/auth/register",
            json={"email": email, "password": _PASSWORD, "displayName": key, "role": role},
        )
        assert register.status_code == 201, register.text
        login = client.post("/api/v2/auth/login", json={"email": email, "password": _PASSWORD})
        assert login.status_code == 200, login.text
        token = login.json()["accessToken"]
        uid = db.scalar(select(User.id).where(User.email == email))
        created[key] = {"uid": uid, "token": token, "email": email}

    yield created

    user_ids = [p["uid"] for p in created.values()]

    # Cases created by any of these test users — cascades case_members/
    # hearings/documents/invites via their ondelete="CASCADE" FKs
    # (app/db/models.py).
    for case in db.scalars(select(Case).where(Case.created_by.in_(user_ids))):
        db.delete(case)
    db.commit()

    # invite_attempts.case_id is ON DELETE SET NULL, not CASCADE, and
    # attempted_by has no ondelete at all — rows referencing these users
    # survive the case deletion above and would block deleting the users
    # themselves.
    db.query(InviteAttempt).filter(InviteAttempt.attempted_by.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.commit()

    # refresh_tokens cascades from users.id automatically.
    db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_full_relationship_graph(client, people, db, ws_client):
    advocate = people["advocate"]
    ngo = people["ngo"]
    family_a = people["family_a"]
    family_b = people["family_b"]

    # 2. Advocate creates a case — ownership fields and is_manager.
    create = client.post(
        "/api/v2/cases",
        json={"undertrialName": "Rel Test Case", "firNumber": "RT-1", "court": "Test Court"},
        headers=_headers(advocate["token"]),
    )
    assert create.status_code == 200, create.text
    case_id = uuid.UUID(create.json()["caseId"])

    case = db.get(Case, case_id)
    assert case.created_by == advocate["uid"]
    assert case.owner_type == "advocate"

    member = db.get(CaseMember, {"case_id": case_id, "user_id": advocate["uid"]})
    assert member is not None
    assert member.role == "advocate"
    assert member.is_manager is True

    # 3. Advocate generates an invite; family_a redeems it; can read,
    # cannot mint invites or add hearings.
    invite = client.post(
        f"/api/v2/cases/{case_id}/invites", headers=_headers(advocate["token"])
    )
    assert invite.status_code == 200, invite.text
    code = invite.json()["code"]

    redeem_a = client.post(
        "/api/v2/invites/redeem", json={"code": code}, headers=_headers(family_a["token"])
    )
    assert redeem_a.status_code == 200, redeem_a.text
    assert redeem_a.json()["caseId"] == str(case_id)

    read_as_a = client.get(f"/api/v2/cases/{case_id}", headers=_headers(family_a["token"]))
    assert read_as_a.status_code == 200

    invite_as_a = client.post(
        f"/api/v2/cases/{case_id}/invites", headers=_headers(family_a["token"])
    )
    assert invite_as_a.status_code == 403

    hearing_as_a = client.post(
        f"/api/v2/cases/{case_id}/hearings",
        json={"date": "2026-12-01T00:00:00Z"},
        headers=_headers(family_a["token"]),
    )
    assert hearing_as_a.status_code == 403

    # Single-use holds across different users, not just against the same
    # user retrying (test_invites.py's existing coverage of the
    # already-redeemed case is same-user only).
    redeem_b_same_code = client.post(
        "/api/v2/invites/redeem", json={"code": code}, headers=_headers(family_b["token"])
    )
    assert redeem_b_same_code.status_code == 409
    member_b_via_code = db.get(CaseMember, {"case_id": case_id, "user_id": family_b["uid"]})
    assert member_b_via_code is None

    # 4. Family_b, who redeemed nothing, gets 403 on this case — the
    # single most important assertion in this suite.
    read_as_b = client.get(f"/api/v2/cases/{case_id}", headers=_headers(family_b["token"]))
    assert read_as_b.status_code == 403

    # 5. Family_b creates their own self-managed case; advocate gets 403
    # on it; family_b is its manager.
    create_b = client.post(
        "/api/v2/cases",
        json={"undertrialName": "Family B's own case"},
        headers=_headers(family_b["token"]),
    )
    assert create_b.status_code == 200, create_b.text
    case_b_id = uuid.UUID(create_b.json()["caseId"])

    read_b_as_advocate = client.get(
        f"/api/v2/cases/{case_b_id}", headers=_headers(advocate["token"])
    )
    assert read_b_as_advocate.status_code == 403

    member_b_own = db.get(CaseMember, {"case_id": case_b_id, "user_id": family_b["uid"]})
    assert member_b_own is not None
    assert member_b_own.is_manager is True

    # 6. NGO, never added to the advocate's case, gets 403 on it.
    read_as_ngo = client.get(f"/api/v2/cases/{case_id}", headers=_headers(ngo["token"]))
    assert read_as_ngo.status_code == 403

    # 7. Advocate adds a hearing; the invalidation reaches family_a
    # (a subscribed member) and does NOT reach family_b (not a member —
    # in fact family_b's socket can't even connect to this case's channel
    # at all, the WS-layer equivalent of step 4's HTTP 403).
    with pytest.raises(Exception):
        with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as fam_b_ws:
            fam_b_ws.send_json({"accessToken": family_b["token"]})
            fam_b_ws.receive_text()  # server closes — raises

    with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as fam_a_ws:
        fam_a_ws.send_json({"accessToken": family_a["token"]})
        time.sleep(0.2)  # let the subscription land before the write below

        add_hearing = client.post(
            f"/api/v2/cases/{case_id}/hearings",
            json={"date": "2026-12-01T00:00:00Z", "purpose": "Arguments"},
            headers=_headers(advocate["token"]),
        )
        assert add_hearing.status_code == 200, add_hearing.text

        message = fam_a_ws.receive_json()
        assert message == {"type": "hearings_changed", "caseId": str(case_id)}
