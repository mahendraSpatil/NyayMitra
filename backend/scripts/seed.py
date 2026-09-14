"""Provisions the three NyayMitra test accounts and CLAUDE.md's demo data.

Usage:
    GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json python seed.py

Never point GOOGLE_APPLICATION_CREDENTIALS at a key committed to this repo.
"""

import os
import sys
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import auth, credentials, firestore

PROJECT_ID = "nyaymitra-ai-92fcc"
DATABASE_ID = "default"  # named Firestore database, not the classic "(default)"
DEV_PASSWORD = "NyayMitra@Dev1"

TEST_ACCOUNTS = [
    {
        "key": "advocate",
        "email": "advocate@nyaymitra.test",
        "display_name": "Adv. Rajesh Sharma",
        "role": "advocate",
    },
    {
        "key": "ngo",
        "email": "ngo@nyaymitra.test",
        "display_name": "NGO Field Worker",
        "role": "ngo",
    },
    {
        "key": "family",
        "email": "family@nyaymitra.test",
        "display_name": "Kumar Family",
        "role": "family",
    },
]


def get_or_create_user(email: str, display_name: str) -> auth.UserRecord:
    try:
        user = auth.get_user_by_email(email)
        print(f"  found existing user {email} ({user.uid})")
        return user
    except auth.UserNotFoundError:
        user = auth.create_user(
            email=email, password=DEV_PASSWORD, display_name=display_name
        )
        print(f"  created user {email} ({user.uid})")
        return user


def seed_accounts(db) -> dict[str, str]:
    uids: dict[str, str] = {}
    for account in TEST_ACCOUNTS:
        user = get_or_create_user(account["email"], account["display_name"])
        auth.set_custom_user_claims(user.uid, {"role": account["role"]})
        db.collection("users").document(user.uid).set(
            {
                "role": account["role"],
                "displayName": account["display_name"],
                "phone": None,
                "preferredLanguage": None,
            }
        )
        uids[account["key"]] = user.uid
    return uids


def seed_demo_data(db, uids: dict[str, str]) -> None:
    advocate_uid = uids["advocate"]
    ngo_uid = uids["ngo"]
    family_uid = uids["family"]

    db.collection("cases").document("case-ramesh-kumar").set(
        {
            "firNumber": "104/2025",
            "court": "District Court Pune",
            "undertrialName": "Ramesh Kumar",
            "advocateUid": advocate_uid,
            "advocateName": "Adv. Rajesh Sharma",
            "familyUids": [family_uid],
            "stage": "bail",
            "stageLabel": "Bail Stage",
            "stageTone": "warning",
            "nextHearingDate": datetime(2026, 10, 24, tzinfo=timezone.utc),
            "documentCount": 0,
            "timeline": [
                {
                    "title": "Charge Sheet Filed",
                    "date": datetime(2025, 8, 12, tzinfo=timezone.utc),
                    "done": True,
                },
                {
                    "title": "Bail Application Submitted",
                    "date": datetime(2025, 9, 5, tzinfo=timezone.utc),
                    "done": True,
                },
                {
                    "title": "Hearing on Arguments",
                    "date": datetime(2026, 10, 24, tzinfo=timezone.utc),
                    "done": False,
                },
            ],
        }
    )

    db.collection("cases").document("case-amit-singh").set(
        {
            "firNumber": "89/2025",
            "court": "Sessions Court Mumbai",
            "undertrialName": "Amit Singh",
            "advocateUid": advocate_uid,
            "advocateName": "Adv. Rajesh Sharma",
            "familyUids": [],
            "stage": "document_review",
            "stageLabel": "Document Review",
            "stageTone": "info",
            "nextHearingDate": datetime(2026, 11, 2, tzinfo=timezone.utc),
            "documentCount": 0,
            "timeline": [],
        }
    )

    db.collection("tasks").document("task-bail-bond-translation").set(
        {
            "assignedToUid": ngo_uid,
            "caseId": "case-ramesh-kumar",
            "taskType": "translation",
            "priority": "high",
            "description": "Bail-bond translation for the Kumar family",
            "completed": False,
            "completedAt": None,
        }
    )

    db.collection("tasks").document("task-legal-aid-coordination").set(
        {
            "assignedToUid": ngo_uid,
            "caseId": "case-amit-singh",
            "taskType": "legal_aid_coordination",
            "priority": "medium",
            "description": "Legal aid coordination for Amit Singh",
            "completed": False,
            "completedAt": None,
        }
    )

    db.collection("tasks").document("task-yerwada-verification").set(
        {
            "assignedToUid": ngo_uid,
            "caseId": "case-ramesh-kumar",
            "taskType": "verification_visit",
            "priority": "scheduled",
            "description": "Yerwada Jail verification visit under 436A",
            "completed": False,
            "completedAt": None,
        }
    )


def main() -> None:
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        sys.exit(
            "GOOGLE_APPLICATION_CREDENTIALS is not set. Point it at a service "
            "account key outside this repo before running seed.py."
        )

    cred = credentials.ApplicationDefault()
    app = firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    db = firestore.client(app=app, database_id=DATABASE_ID)

    print("Seeding test accounts...")
    uids = seed_accounts(db)

    print("Seeding demo data...")
    seed_demo_data(db, uids)

    print("\nDone. Test account credentials (dev only):")
    for account in TEST_ACCOUNTS:
        print(f"  {account['role']:<10} {account['email']}  /  {DEV_PASSWORD}")


if __name__ == "__main__":
    main()
