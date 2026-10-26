"""Admin utility: resets one user's password directly against Postgres,
for when you need a known-good credential to test with and can no longer
be sure what's actually stored. Same hash_password() as registration
(app/security/passwords.py) and /auth/login's register/login handlers —
this is not a separate, weaker path, just a shortcut around the HTTP API
for when the HTTP API is exactly the thing you can't get into.

Does not enforce app/security/password_policy.py's rules (length,
deny-list) — this is an operator running it deliberately against a
specific account, not a public endpoint that needs to be defended against
whatever a caller submits.

Usage:
    python scripts/reset_password.py <email> <new-password>

DATABASE_URL is normally already set in backend/.env (loaded via
app.config), so just:
    python scripts/reset_password.py lawyer01@test.com TestPass123456
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import settings
from app.db.base import SessionLocal, engine
from app.db.models import User
from app.security.passwords import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("new_password")
    args = parser.parse_args()

    if not settings.database_url:
        sys.exit(
            "DATABASE_URL is not set. Copy backend/.env.example to backend/.env "
            "and fill it in before running reset_password.py."
        )
    if engine is None:
        sys.exit("Could not create a database engine from DATABASE_URL.")

    # Same normalization /auth/login and /auth/register apply
    # (app/models/auth.py's _normalize_email) — looking this up
    # case/whitespace-sensitively would risk "found no such user" even
    # when one exists, or silently resetting the wrong row's near-miss
    # twin if two differently-cased rows ever existed.
    email = args.email.strip().lower()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            sys.exit(f"No user found with email {email!r}.")

        user.password_hash = hash_password(args.new_password)
        db.commit()

    print(f"Password reset for {email} (role={user.role}, id={user.id}).")


if __name__ == "__main__":
    main()
