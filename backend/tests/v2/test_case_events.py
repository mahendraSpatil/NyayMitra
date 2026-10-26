"""GET/POST /cases/{caseId}/events — case_events' first write path.
See NyayMitra.md's Postgres schema notes: case_events is the non-hearing
half of the Case Timeline the Flutter client merges client-side.

Run with: pytest tests/v2/test_case_events.py -v
"""

import time

from app.db.models import CaseMember


def _advocate_owned_case(make_case, accounts, db):
    case_id = make_case(created_by=accounts["advocate"]["uid"], owner_type="advocate")
    db.add(CaseMember(case_id=case_id, user_id=accounts["advocate"]["uid"], role="advocate", is_manager=True))
    db.commit()
    return case_id


def test_manager_can_add_an_event_and_it_appears_in_the_list(
    client, auth_headers, make_case, accounts, db
):
    case_id = _advocate_owned_case(make_case, accounts, db)

    add = client.post(
        f"/api/v2/cases/{case_id}/events",
        json={"title": "Charge sheet filed", "date": "2026-10-01T00:00:00Z", "eventType": "charge_sheet_filed"},
        headers=auth_headers("advocate"),
    )
    assert add.status_code == 200, add.text
    event_id = add.json()["eventId"]

    listing = client.get(f"/api/v2/cases/{case_id}/events", headers=auth_headers("advocate"))
    assert listing.status_code == 200
    events = listing.json()
    assert len(events) == 1
    assert events[0]["id"] == event_id
    assert events[0]["title"] == "Charge sheet filed"
    assert events[0]["eventType"] == "charge_sheet_filed"
    assert events[0]["done"] is False


def test_non_manager_member_cannot_add_an_event(client, auth_headers, make_case, accounts, db):
    """A family member who joined via invite can read the timeline but
    not write to it — same member/manager split as hearings.
    """
    case_id = _advocate_owned_case(make_case, accounts, db)
    db.add(CaseMember(case_id=case_id, user_id=accounts["family"]["uid"], role="family", is_manager=False))
    db.commit()

    add = client.post(
        f"/api/v2/cases/{case_id}/events",
        json={"title": "Bail application submitted"},
        headers=auth_headers("family"),
    )
    assert add.status_code == 403

    read = client.get(f"/api/v2/cases/{case_id}/events", headers=auth_headers("family"))
    assert read.status_code == 200
    assert read.json() == []


def test_non_member_cannot_read_or_write_events(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)

    read = client.get(f"/api/v2/cases/{case_id}/events", headers=auth_headers("ngo"))
    assert read.status_code == 403

    add = client.post(
        f"/api/v2/cases/{case_id}/events", json={"title": "x"}, headers=auth_headers("ngo")
    )
    assert add.status_code == 403


def test_invalid_event_type_is_rejected(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)

    add = client.post(
        f"/api/v2/cases/{case_id}/events",
        json={"title": "x", "eventType": "not-a-real-type"},
        headers=auth_headers("advocate"),
    )
    assert add.status_code == 422


def test_events_without_a_date_sort_last(client, auth_headers, make_case, accounts, db):
    case_id = _advocate_owned_case(make_case, accounts, db)

    client.post(
        f"/api/v2/cases/{case_id}/events",
        json={"title": "No date yet"},
        headers=auth_headers("advocate"),
    )
    client.post(
        f"/api/v2/cases/{case_id}/events",
        json={"title": "Dated", "date": "2026-01-01T00:00:00Z"},
        headers=auth_headers("advocate"),
    )

    listing = client.get(f"/api/v2/cases/{case_id}/events", headers=auth_headers("advocate"))
    titles = [e["title"] for e in listing.json()]
    assert titles == ["Dated", "No date yet"]


def test_add_event_broadcasts_case_events_changed(ws_client, auth_headers, make_case, accounts, db):
    """Mirrors test_ws.py's hearing-invalidation test — proves the new
    write path actually notifies live subscribers, not just that the row
    lands in Postgres.
    """
    case_id = _advocate_owned_case(make_case, accounts, db)
    adv_token = accounts["advocate"]["access_token"]

    with ws_client.websocket_connect(f"/api/v2/ws/cases/{case_id}") as ws:
        ws.send_json({"accessToken": adv_token})
        time.sleep(0.2)  # let the subscription land before the write below

        response = ws_client.post(
            f"/api/v2/cases/{case_id}/events",
            json={"title": "Bail order issued", "eventType": "bail_order_issued"},
            headers=auth_headers("advocate"),
        )
        assert response.status_code == 200

        message = ws.receive_json()
        assert message == {"type": "case_events_changed", "caseId": str(case_id)}
