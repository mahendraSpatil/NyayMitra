"""Email normalization for /auth/login and /auth/register — a trailing
space from a paste, or a capitalized first letter some platform's
autofill added, must never make a correct password look wrong. See
app/models/auth.py's _normalize_email (LoginRequest/RegisterRequest) and
client/lib/core/services/auth_service.dart's matching client-side copy.

Run with: pytest tests/v2/test_auth.py -v
"""

from app.db.models import User

_PASSWORD = "NyayMitra@Dev1"  # matches scripts/seed.py's seeded accounts


def test_login_normalizes_whitespace_and_case(client):
    response = client.post(
        "/api/v2/auth/login",
        json={"email": "  Advocate@NyayMitra.Test  ", "password": _PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "advocate"


def test_register_stores_normalized_email_and_rejects_case_variant_duplicate(client, db):
    email = "reg-norm-test@example.com"
    padded_mixed_case = f"  {email.upper()}  "

    register = client.post(
        "/api/v2/auth/register",
        json={
            "email": padded_mixed_case,
            "password": "A-Genuinely-Long-Password-1",
            "displayName": "Norm Test",
            "role": "family",
        },
    )
    assert register.status_code == 201, register.text
    assert register.json()["email"] == email  # stored normalized, not as typed

    try:
        # A differently-cased/padded attempt at the *same* email must be
        # caught by the duplicate check, not slip past it as "different".
        duplicate = client.post(
            "/api/v2/auth/register",
            json={
                "email": f" {email} ",
                "password": "A-Different-Long-Password-2",
                "displayName": "Norm Test Again",
                "role": "family",
            },
        )
        assert duplicate.status_code == 409

        # And login works with the plain, unpadded, lowercase form even
        # though registration was submitted padded and upper-cased.
        login = client.post(
            "/api/v2/auth/login", json={"email": email, "password": "A-Genuinely-Long-Password-1"}
        )
        assert login.status_code == 200, login.text
    finally:
        db.query(User).filter(User.email == email).delete(synchronize_session=False)
        db.commit()
