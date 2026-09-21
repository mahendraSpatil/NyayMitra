"""Access + refresh token machinery.

Access tokens are short-lived JWTs (sub + role), verified on every
request by app/dependencies.py's get_current_user — the replacement for
Firebase's verify_id_token, once routes are ported onto it (step 3).

Refresh tokens are NOT JWTs: they're opaque random values, handed to the
client once and never decoded — only ever looked up by the SHA-256 hash
of what the client presents back at /auth/refresh, against the
refresh_tokens table (app/db/models.py). They're already
high-entropy random values, not something an attacker brute-forces
offline the way a human password is, so Argon2's deliberate slowness
would only add latency to every /auth/refresh call for no benefit —
SHA-256 (fast, and that's fine here) is the right tool, not the one used
for passwords.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from ..config import settings

ACCESS_TOKEN_TTL = timedelta(minutes=15)
# Not specified by the migration brief — 30 days chosen as a reasonable
# default for a mobile-ish app that shouldn't force frequent re-logins;
# revisit if that assumption turns out wrong.
REFRESH_TOKEN_TTL = timedelta(days=30)

_ALGORITHM = "HS256"


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError (ExpiredSignatureError, InvalidTokenError,
    ...) on anything wrong — callers turn that into a 401, never a 500:
    an expired or tampered token is an expected, routine occurrence, not
    a server error.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
