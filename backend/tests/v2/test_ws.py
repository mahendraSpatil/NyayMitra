"""Live WebSocket tests against a real Postgres-backed app — connection
handshake, case-membership authorization, broadcast delivery on both
channels, the removed-from-case close, and token-expiry close.

Run with: pytest tests/v2/test_ws.py -v
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.models import CaseMember
from app.main import app
from app.security import ws_auth
from app.services.v2.connections import manager as ws_manager


def _advocate_owned_case(make_case, accounts, db):
    case_id = make_case(created_by=accounts["advocate"]["uid"], owner_type="advocate")
    db.add(CaseMember(case_id=case_id, user_id=accounts["advocate"]["uid"], role="advocate", is_manager=True))
    db.commit()
    return case_id


def _short_lived_token(user_id: uuid.UUID, role: str, *, seconds: float) -> str:
    """A token expiring in [seconds] — for exercising the expiry-close
    path without waiting out a real 15-minute access token.
    """
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(seconds=seconds)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


@pytest.fixture
def ws_client():
    """Context-managed, unlike the plain `client` fixture in conftest.py
    — lifespan startup (which binds the connections manager to the event
    loop, main.py) and WebSocket support both need the `with` form.
    """
    with TestClient(app) as c:
        yield c


def test_case_member_can_connect_and_non_member_is_rejected(
    ws_client, auth_headers, accounts, make_case, db
):
    case_id = _advocate_owned_case(make_case, accounts, db)
    adv_token = accounts["advocate"]["access_token"]
    ngo_token = accounts["ngo"]["access_token"]

    with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as ws:
        ws.send_json({"accessToken": adv_token})
        # No message means the handshake succeeded and the server is
        # just holding the connection open (server-to-client only
        # channel) — proven by the fact this doesn't raise/close.
        time.sleep(0.2)

    with pytest.raises(Exception):
        with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as ws:
            ws.send_json({"accessToken": ngo_token})
            ws.receive_text()  # server closes; TestClient surfaces that as an exception here


def test_handshake_times_out_without_a_token(ws_client, make_case, accounts, db, monkeypatch):
    monkeypatch.setattr(ws_auth, "HANDSHAKE_TIMEOUT_SECONDS", 0.3)
    case_id = _advocate_owned_case(make_case, accounts, db)

    with pytest.raises(Exception):
        with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as ws:
            ws.receive_text()  # never sent a token — server closes after the (shortened) timeout


def test_hearing_write_broadcasts_invalidation_to_the_other_case_subscriber(
    ws_client, auth_headers, accounts, make_case, db
):
    """The actual point of this whole channel: two different users
    watching the same case, one writes (over plain REST, same as any
    other client action), the other finds out over the socket — without
    ever being sent the hearing data itself, only the invalidation.
    """
    case_id = _advocate_owned_case(make_case, accounts, db)
    db.add(CaseMember(case_id=case_id, user_id=accounts["family"]["uid"], role="family", is_manager=False))
    db.commit()

    adv_token = accounts["advocate"]["access_token"]
    fam_token = accounts["family"]["access_token"]

    with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as adv_ws:
        adv_ws.send_json({"accessToken": adv_token})
        with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as fam_ws:
            fam_ws.send_json({"accessToken": fam_token})
            time.sleep(0.2)  # let both subscriptions land before the write

            response = ws_client.post(
                f"/api/v2/cases/{case_id}/hearings",
                json={"date": "2026-12-01T00:00:00Z", "purpose": "Arguments"},
                headers=auth_headers("advocate"),
            )
            assert response.status_code == 200

            message = fam_ws.receive_json()
            assert message == {"type": "hearings_changed", "caseId": str(case_id)}


def test_me_channel_receives_tasks_changed_on_completion(ws_client, auth_headers, accounts, db):
    from app.db.models import Task

    task = db.scalar(select(Task).where(Task.assigned_to_uid == accounts["ngo"]["uid"], Task.completed.is_(False)))
    assert task is not None, "expected an incomplete seeded task assigned to the NGO account"

    ngo_token = accounts["ngo"]["access_token"]

    with ws_client.websocket_connect("/api/v2/ws/me") as ws:
        ws.send_json({"accessToken": ngo_token})
        time.sleep(0.2)

        response = ws_client.patch(f"/api/v2/tasks/{task.id}/complete", headers=auth_headers("ngo"))
        assert response.status_code == 200

        message = ws.receive_json()
        assert message == {"type": "tasks_changed"}

    # Reset so this test is safe to re-run — db.refresh() first because
    # the API call above committed the completion through a *different*
    # session (get_db() opens a fresh one per request); this session's
    # copy of `task` is stale (expire_on_commit=False, db/base.py) and
    # still shows completed=False in memory. Setting completed = False
    # against that stale in-memory value is a same-value no-op SQLAlchemy
    # won't consider dirty, so it silently skips the UPDATE — caught this
    # exact way, by checking the database afterward rather than trusting
    # the test's own "reset" line ran.
    db.refresh(task)
    task.completed = False
    task.completed_at = None
    db.commit()


def test_expired_token_closes_the_socket(ws_client, accounts):
    token = _short_lived_token(accounts["advocate"]["uid"], "advocate", seconds=0.5)

    with pytest.raises(Exception):
        with ws_client.websocket_connect("/api/v2/ws/me") as ws:
            ws.send_json({"accessToken": token})
            time.sleep(1.0)  # past the token's expiry
            ws.receive_text()  # the server should have closed by now


def test_close_case_sockets_for_user_disconnects_a_removed_member(
    ws_client, make_case, accounts, db
):
    """No endpoint removes a case_member today — there's no "remove
    someone from a case" feature yet — so this calls the connection
    manager's primitive directly rather than through a real removal
    endpoint. It proves the mechanism (app/services/v2/connections.py's
    close_case_sockets_for_user) works, ready for whenever that feature
    exists.
    """
    case_id = _advocate_owned_case(make_case, accounts, db)
    db.add(CaseMember(case_id=case_id, user_id=accounts["family"]["uid"], role="family", is_manager=False))
    db.commit()

    fam_token = accounts["family"]["access_token"]

    with pytest.raises(Exception):
        with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as ws:
            ws.send_json({"accessToken": fam_token})
            time.sleep(0.2)

            db.query(CaseMember).filter(
                CaseMember.case_id == case_id, CaseMember.user_id == accounts["family"]["uid"]
            ).delete()
            db.commit()

            future = asyncio.run_coroutine_threadsafe(
                ws_manager.close_case_sockets_for_user(case_id, accounts["family"]["uid"], code=4403),
                ws_manager._loop,
            )
            future.result(timeout=2)

            ws.receive_text()  # closed — raises
