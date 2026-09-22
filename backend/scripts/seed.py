"""Provisions the three NyayMitra test accounts and NyayMitra.md's demo
data, against Postgres. Same accounts, same two demo cases, same three
tasks as the old Firestore-backed seed.py this replaced (step 6 of the
Postgres migration — Firebase is gone, this is the only seed script now).

Usage:
    DATABASE_URL=postgresql+psycopg://... python seed.py

DATABASE_URL is normally already set in backend/.env (loaded via
app.config), so just:
    python seed.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import SessionLocal, engine
from app.db.models import Case, CaseEvent, CaseMember, Hearing, Task, User
from app.security.passwords import hash_password

DEV_PASSWORD = "NyayMitra@Dev1"

TEST_ACCOUNTS = [
    {"key": "advocate", "email": "advocate@nyaymitra.test", "display_name": "Adv. Rajesh Sharma", "role": "advocate"},
    {"key": "ngo", "email": "ngo@nyaymitra.test", "display_name": "NGO Field Worker", "role": "ngo"},
    {"key": "family", "email": "family@nyaymitra.test", "display_name": "Kumar Family", "role": "family"},
]


def get_or_create_user(db: Session, email: str, display_name: str, role: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        print(f"  found existing user {email} ({user.id})")
        return user
    user = User(
        email=email,
        password_hash=hash_password(DEV_PASSWORD),
        role=role,
        display_name=display_name,
    )
    db.add(user)
    db.flush()  # assigns user.id without committing yet
    print(f"  created user {email} ({user.id})")
    return user


def seed_accounts(db: Session) -> dict[str, User]:
    users: dict[str, User] = {}
    for account in TEST_ACCOUNTS:
        users[account["key"]] = get_or_create_user(
            db, account["email"], account["display_name"], account["role"]
        )
    return users


def get_or_create_case(db: Session, *, fir_number: str, **fields) -> Case:
    """Keyed on fir_number, the closest thing this schema has to
    Firestore's human-readable document-id slugs (case-ramesh-kumar) —
    re-running this script is a no-op against an already-seeded database
    rather than creating duplicate demo cases each time.
    """
    case = db.scalar(select(Case).where(Case.fir_number == fir_number))
    if case is not None:
        print(f"  found existing case {fir_number} ({case.id})")
        return case
    case = Case(fir_number=fir_number, **fields)
    db.add(case)
    db.flush()
    print(f"  created case {fir_number} ({case.id})")
    return case


def seed_demo_data(db: Session, users: dict[str, User]) -> None:
    advocate = users["advocate"]
    ngo = users["ngo"]
    family = users["family"]

    ramesh = get_or_create_case(
        db,
        fir_number="104/2025",
        court="District Court Pune",
        undertrial_name="Ramesh Kumar",
        created_by=advocate.id,
        owner_type="advocate",
        stage="bail",
        stage_label="Bail Stage",
        stage_tone="warning",
        next_hearing_date=datetime(2026, 10, 24, tzinfo=timezone.utc),
        document_count=0,
    )

    amit = get_or_create_case(
        db,
        fir_number="89/2025",
        court="Sessions Court Mumbai",
        undertrial_name="Amit Singh",
        created_by=advocate.id,
        owner_type="advocate",
        stage="document_review",
        stage_label="Document Review",
        stage_tone="info",
        next_hearing_date=datetime(2026, 11, 2, tzinfo=timezone.utc),
        document_count=0,
    )

    # case_members — replaces Firestore's advocateUid/familyUids/ngoUids
    # fields on the case doc. is_manager mirrors exactly what
    # is_case_manager() used to compute: true for the advocate, true for
    # every NGO member, true for a family member only if they created the
    # case themselves. Both demo cases were advocate-created, so the
    # family member on Ramesh Kumar's case (who did NOT create it) is a
    # member but not a manager — same as before this migration.
    _ensure_member(db, ramesh, advocate, role="advocate", is_manager=True)
    _ensure_member(db, ramesh, family, role="family", is_manager=False)
    _ensure_member(db, amit, advocate, role="advocate", is_manager=True)

    # hearings — only the actual hearing dates from the old timeline;
    # "Charge Sheet Filed" and "Bail Application Submitted" were never
    # hearings, they're case_events below. Ramesh Kumar's "Hearing on
    # Arguments" entry (2026-10-24) IS the case's nextHearingDate, so it
    # becomes the one hearings row; Amit Singh's case had a
    # nextHearingDate with no matching timeline entry at all in the old
    # data (an inconsistency in seed.py, not reproduced here) — still
    # needs a hearings row so nextHearingDate stays truthfully derived
    # from an actual hearing rather than a bare field with nothing behind
    # it.
    _ensure_hearing(
        db, ramesh, date=datetime(2026, 10, 24, tzinfo=timezone.utc),
        court="District Court Pune", purpose="Arguments", status="scheduled",
    )
    _ensure_hearing(
        db, amit, date=datetime(2026, 11, 2, tzinfo=timezone.utc),
        court="Sessions Court Mumbai", purpose="", status="scheduled",
    )

    # case_events — non-hearing timeline entries, replacing cases.timeline.
    _ensure_event(db, ramesh, title="Charge Sheet Filed", event_date=datetime(2025, 8, 12, tzinfo=timezone.utc), done=True)
    _ensure_event(db, ramesh, title="Bail Application Submitted", event_date=datetime(2025, 9, 5, tzinfo=timezone.utc), done=True)

    _ensure_task(
        db, assigned_to=ngo, case=ramesh, task_type="translation", priority="high",
        description="Bail-bond translation for the Kumar family",
    )
    _ensure_task(
        db, assigned_to=ngo, case=amit, task_type="legal_aid_coordination", priority="medium",
        description="Legal aid coordination for Amit Singh",
    )
    _ensure_task(
        db, assigned_to=ngo, case=ramesh, task_type="verification_visit", priority="scheduled",
        description="Yerwada Jail verification visit under 436A",
    )


def _ensure_member(db: Session, case: Case, user: User, *, role: str, is_manager: bool) -> None:
    existing = db.get(CaseMember, {"case_id": case.id, "user_id": user.id})
    if existing is not None:
        return
    db.add(CaseMember(case_id=case.id, user_id=user.id, role=role, is_manager=is_manager))


def _ensure_hearing(db: Session, case: Case, **fields) -> None:
    existing = db.scalar(
        select(Hearing).where(Hearing.case_id == case.id, Hearing.date == fields["date"])
    )
    if existing is not None:
        return
    db.add(Hearing(case_id=case.id, **fields))


def _ensure_event(db: Session, case: Case, *, title: str, **fields) -> None:
    existing = db.scalar(
        select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.title == title)
    )
    if existing is not None:
        return
    db.add(CaseEvent(case_id=case.id, title=title, **fields))


def _ensure_task(db: Session, *, assigned_to: User, case: Case, task_type: str, **fields) -> None:
    existing = db.scalar(
        select(Task).where(
            Task.assigned_to_uid == assigned_to.id, Task.case_id == case.id, Task.task_type == task_type
        )
    )
    if existing is not None:
        return
    db.add(Task(assigned_to_uid=assigned_to.id, case_id=case.id, task_type=task_type, **fields))


def main() -> None:
    if not settings.database_url:
        sys.exit(
            "DATABASE_URL is not set. Copy backend/.env.example to backend/.env "
            "and fill it in before running seed.py."
        )
    if engine is None:
        sys.exit("Could not create a database engine from DATABASE_URL.")

    with SessionLocal() as db:
        print("Seeding test accounts...")
        users = seed_accounts(db)

        print("Seeding demo data...")
        seed_demo_data(db, users)

        db.commit()

    print("\nDone. Test account credentials (dev only):")
    for account in TEST_ACCOUNTS:
        print(f"  {account['role']:<10} {account['email']}  /  {DEV_PASSWORD}")


if __name__ == "__main__":
    main()
