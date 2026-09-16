"""Recomputes cases/{caseId}'s denormalised nextHearingDate from its
hearings subcollection. Called after every hearing add/edit/delete —
nextHearingDate is a convenience for list/sort queries that must never
drift from the hearings it's derived from.
"""


def recompute_next_hearing_date(db, case_id: str):
    """Returns the new value (a datetime or None) after writing it onto
    the parent case. The soonest 'scheduled' hearing wins; hearings marked
    completed/adjourned/cancelled are never the case's "next" hearing.
    """
    hearings_ref = db.collection("cases").document(case_id).collection("hearings")
    next_date = None
    for snap in hearings_ref.where("status", "==", "scheduled").stream():
        date = (snap.to_dict() or {}).get("date")
        if date is not None and (next_date is None or date < next_date):
            next_date = date

    db.collection("cases").document(case_id).update({"nextHearingDate": next_date})
    return next_date
