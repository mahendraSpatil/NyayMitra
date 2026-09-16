"""Real, re-runnable tests against the live Firebase project for the part
of this phase that mattered most to get right: invite generation and
redemption. Run with `pytest tests/test_invites.py` from backend/, with
the venv active and backend/.env's FIREBASE_WEB_API_KEY set.
"""

from datetime import datetime, timedelta, timezone

from app.services.invites import GENERATION_LIMIT_PER_CASE


def _advocate_owned_case(make_case, accounts):
    return make_case(
        advocateUid=accounts["advocate"]["uid"],
        advocateName="Adv. Rajesh Sharma",
        createdBy=accounts["advocate"]["uid"],
        ownerType="advocate",
    )


def test_family_can_redeem_a_freshly_generated_code(client, auth_headers, make_case, accounts):
    case_id = _advocate_owned_case(make_case, accounts)

    generate = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate"))
    assert generate.status_code == 200
    code = generate.json()["code"]

    redeem = client.post("/invites/redeem", json={"code": code}, headers=auth_headers("family"))
    assert redeem.status_code == 200
    assert redeem.json()["caseId"] == case_id


def test_redeeming_an_expired_code_is_rejected(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts)

    generate = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate"))
    code = generate.json()["code"]

    # Backdate the code's expiry directly — waiting 24 real hours for this
    # test isn't practical, and this exercises the same expiry check the
    # endpoint runs regardless of how the code got old.
    invite_doc = next(db.collection("invites").where("caseId", "==", case_id).stream())
    invite_doc.reference.update({"expiresAt": datetime.now(timezone.utc) - timedelta(hours=1)})

    redeem = client.post("/invites/redeem", json={"code": code}, headers=auth_headers("family"))
    assert redeem.status_code == 410

    case_after = db.collection("cases").document(case_id).get().to_dict()
    assert accounts["family"]["uid"] not in (case_after.get("familyUids") or [])


def test_redeeming_an_already_redeemed_code_is_rejected(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts)

    generate = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate"))
    code = generate.json()["code"]

    first = client.post("/invites/redeem", json={"code": code}, headers=auth_headers("family"))
    assert first.status_code == 200

    second = client.post("/invites/redeem", json={"code": code}, headers=auth_headers("family"))
    assert second.status_code == 409

    case_after = db.collection("cases").document(case_id).get().to_dict()
    # Single-use, not a duplicate-tolerant array add: exactly one entry,
    # not two, even though the redeeming uid is the same both times.
    assert case_after.get("familyUids") == [accounts["family"]["uid"]]


def test_redeeming_an_unknown_code_is_rejected(client, auth_headers, accounts, db):
    response = client.post(
        "/invites/redeem", json={"code": "not-a-real-code"}, headers=auth_headers("family")
    )
    assert response.status_code == 404

    # Not tied to a case (make_case's teardown wouldn't find it), so
    # clean up this test's own attempt-log record directly.
    for attempt in (
        db.collection("inviteAttempts")
        .where("attemptedBy", "==", accounts["family"]["uid"])
        .where("caseId", "==", None)
        .stream()
    ):
        attempt.reference.delete()


def test_family_member_who_joined_via_invite_cannot_mutate_the_case(
    client, auth_headers, make_case, accounts
):
    """The whole point of the member/manager split: reading a case you
    were invited into must not imply you can add hearings on it.
    """
    case_id = _advocate_owned_case(make_case, accounts)
    code = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]
    client.post("/invites/redeem", json={"code": code}, headers=auth_headers("family"))

    add_hearing = client.post(
        f"/cases/{case_id}/hearings",
        json={"date": "2026-12-01T00:00:00Z"},
        headers=auth_headers("family"),
    )
    assert add_hearing.status_code == 403
    assert "manager" in add_hearing.json()["detail"].lower()


def test_family_member_who_joined_via_invite_cannot_generate_further_invites(
    client, auth_headers, make_case, accounts
):
    case_id = _advocate_owned_case(make_case, accounts)
    code = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]
    client.post("/invites/redeem", json={"code": code}, headers=auth_headers("family"))

    second_invite = client.post(f"/cases/{case_id}/invites", headers=auth_headers("family"))
    assert second_invite.status_code == 403


def test_non_family_role_cannot_redeem(client, auth_headers, make_case, accounts):
    case_id = _advocate_owned_case(make_case, accounts)
    code = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]

    # ngoUids never comes from an invite redemption — only familyUids
    # does (roleToGrant is fixed server-side to 'family') — so an NGO
    # account hitting this endpoint at all is a role confusion.
    redeem = client.post("/invites/redeem", json={"code": code}, headers=auth_headers("ngo"))
    assert redeem.status_code == 403


def test_invite_generation_is_rate_limited_per_case(client, auth_headers, make_case, accounts):
    case_id = _advocate_owned_case(make_case, accounts)

    for _ in range(GENERATION_LIMIT_PER_CASE):
        response = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate"))
        assert response.status_code == 200

    over_limit = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate"))
    assert over_limit.status_code == 429


def test_every_redemption_attempt_is_logged(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts)
    code = client.post(f"/cases/{case_id}/invites", headers=auth_headers("advocate")).json()["code"]

    client.post("/invites/redeem", json={"code": code}, headers=auth_headers("family"))

    attempts = list(db.collection("inviteAttempts").where("caseId", "==", case_id).stream())
    assert len(attempts) == 1
    attempt = attempts[0].to_dict()
    assert attempt["outcome"] == "redeemed"
    assert attempt["attemptedBy"] == accounts["family"]["uid"]
    # The raw code is never stored in the attempt log, only a hash of it.
    assert "code" not in attempt
    assert attempt["codeHash"] != code
