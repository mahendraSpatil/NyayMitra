"""Port of tests/test_invites.py onto /api/v2 + Postgres — same 9
adversarial cases, same standard (real tests, real DB, all passing), plus
one the Firestore version could only ever claim: proof that concurrent
redemption of the same code lets exactly one caller through, backed by
SELECT ... FOR UPDATE (app/services/v2/invites.py) rather than a
Firestore transaction.

Run with: pytest tests/v2/test_invites.py -v
"""

import concurrent.futures
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import CaseMember, Invite, InviteAttempt
from app.main import app
from app.services.v2.invites import GENERATION_LIMIT_PER_CASE


def _advocate_owned_case(make_case, accounts, db):
    case_id = make_case(created_by=accounts["advocate"]["uid"], owner_type="advocate")
    db.add(CaseMember(case_id=case_id, user_id=accounts["advocate"]["uid"], role="advocate", is_manager=True))
    db.commit()
    return case_id


def test_family_can_redeem_a_freshly_generated_code(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)

    generate = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate"))
    assert generate.status_code == 200
    code = generate.json()["code"]

    redeem = client.post("/api/v2/invites/redeem", json={"code": code}, headers=auth_headers("family"))
    assert redeem.status_code == 200
    assert redeem.json()["caseId"] == str(case_id)


def test_redeeming_an_expired_code_is_rejected(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)

    generate = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate"))
    code = generate.json()["code"]

    invite = db.scalar(select(Invite).where(Invite.case_id == case_id))
    invite.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    redeem = client.post("/api/v2/invites/redeem", json={"code": code}, headers=auth_headers("family"))
    assert redeem.status_code == 410

    member = db.get(CaseMember, {"case_id": case_id, "user_id": accounts["family"]["uid"]})
    assert member is None


def test_redeeming_an_already_redeemed_code_is_rejected(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)

    generate = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate"))
    code = generate.json()["code"]

    first = client.post("/api/v2/invites/redeem", json={"code": code}, headers=auth_headers("family"))
    assert first.status_code == 200

    second = client.post("/api/v2/invites/redeem", json={"code": code}, headers=auth_headers("family"))
    assert second.status_code == 409

    # Single-use, not a duplicate-tolerant insert: exactly one
    # case_members row for this family user, not an error and not two.
    members = list(
        db.scalars(
            select(CaseMember).where(
                CaseMember.case_id == case_id, CaseMember.user_id == accounts["family"]["uid"]
            )
        )
    )
    assert len(members) == 1


def test_redeeming_an_unknown_code_is_rejected(client, auth_headers, accounts, db):
    response = client.post(
        "/api/v2/invites/redeem", json={"code": "not-a-real-code"}, headers=auth_headers("family")
    )
    assert response.status_code == 404

    # Not tied to a case (make_case's teardown wouldn't find it, since
    # there never was one), so clean up this test's own attempt-log
    # record directly.
    db.query(InviteAttempt).filter(
        InviteAttempt.case_id.is_(None), InviteAttempt.attempted_by == accounts["family"]["uid"]
    ).delete()
    db.commit()


def test_family_member_who_joined_via_invite_cannot_mutate_the_case(
    client, auth_headers, make_case, accounts, db
):
    """The whole point of the member/manager split: reading a case you
    were invited into must not imply you can add hearings on it.
    """
    case_id = _advocate_owned_case(make_case, accounts, db)
    code = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]
    client.post("/api/v2/invites/redeem", json={"code": code}, headers=auth_headers("family"))

    add_hearing = client.post(
        f"/api/v2/cases/{case_id}/hearings",
        json={"date": "2026-12-01T00:00:00Z"},
        headers=auth_headers("family"),
    )
    assert add_hearing.status_code == 403
    assert "manager" in add_hearing.json()["detail"].lower()


def test_family_member_who_joined_via_invite_cannot_generate_further_invites(
    client, auth_headers, make_case, accounts, db
):
    case_id = _advocate_owned_case(make_case, accounts, db)
    code = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]
    client.post("/api/v2/invites/redeem", json={"code": code}, headers=auth_headers("family"))

    second_invite = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("family"))
    assert second_invite.status_code == 403


def test_non_family_role_cannot_redeem(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)
    code = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]

    # familyUids' Postgres equivalent (case_members with role='family')
    # never comes from an invite redemption for anyone but a family
    # account — roleToGrant is fixed server-side to 'family' — so an NGO
    # account hitting this endpoint at all is a role confusion.
    redeem = client.post("/api/v2/invites/redeem", json={"code": code}, headers=auth_headers("ngo"))
    assert redeem.status_code == 403


def test_invite_generation_is_rate_limited_per_case(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)

    for _ in range(GENERATION_LIMIT_PER_CASE):
        response = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate"))
        assert response.status_code == 200

    over_limit = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate"))
    assert over_limit.status_code == 429


def test_every_redemption_attempt_is_logged(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)
    code = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]

    client.post("/api/v2/invites/redeem", json={"code": code}, headers=auth_headers("family"))

    attempts = list(db.scalars(select(InviteAttempt).where(InviteAttempt.case_id == case_id)))
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.outcome == "redeemed"
    assert attempt.attempted_by == accounts["family"]["uid"]
    # The raw code is never stored in the attempt log, only a hash of it.
    assert attempt.code_hash != code


def test_concurrent_redemption_of_the_same_code_only_one_succeeds(client, auth_headers, make_case, accounts, db):
    """SELECT ... FOR UPDATE (app/services/v2/invites.py's redeem_invite)
    locks the invite row for the rest of the transaction — a second
    concurrent redemption blocks until the first commits, then correctly
    sees the row already redeemed. Fired against the real TestClient (its
    own dedicated app instance per thread, not the shared session-scoped
    `client` fixture, since sharing one TestClient across threads isn't a
    guarantee this suite wants to lean on) so the two requests are
    genuinely concurrent at the database level, not just sequential calls
    dressed up as a "concurrency test".
    """
    case_id = _advocate_owned_case(make_case, accounts, db)
    code = client.post(f"/api/v2/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]
    headers = auth_headers("family")

    def _redeem():
        with TestClient(app) as thread_client:
            return thread_client.post("/api/v2/invites/redeem", json={"code": code}, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_redeem) for _ in range(2)]
        results = [f.result() for f in futures]

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], f"expected exactly one 200 and one 409, got {statuses}"

    # And exactly one case_members row came out of it, not zero and not two.
    members = list(
        db.scalars(
            select(CaseMember).where(
                CaseMember.case_id == case_id, CaseMember.user_id == accounts["family"]["uid"]
            )
        )
    )
    assert len(members) == 1
