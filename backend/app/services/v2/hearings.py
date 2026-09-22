"""Recomputes cases.next_hearing_date from its hearings — the Postgres
equivalent of the deleted Firestore-era hearings service. Called after
every hearing add/edit/delete; next_hearing_date is a denormalised
convenience for list/sort queries that must never drift from the
hearings it's derived from.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import Case, Hearing


def recompute_next_hearing_date(db: Session, case_id: uuid.UUID) -> datetime | None:
    """Returns the new value after writing it onto the parent case. The
    soonest 'scheduled' hearing wins; hearings marked completed/adjourned/
    cancelled are never the case's "next" hearing. Does not commit — the
    caller's own transaction (which already touched the hearing itself)
    covers this write too, so a crash between the two can't happen.
    """
    next_date = db.scalar(
        select(Hearing.date)
        .where(Hearing.case_id == case_id, Hearing.status == "scheduled")
        .order_by(Hearing.date.asc())
        .limit(1)
    )
    case = db.get(Case, case_id)
    case.next_hearing_date = next_date
    return next_date
