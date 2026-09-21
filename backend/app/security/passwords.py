"""Password hashing — Argon2id only, never bcrypt (see NyayMitra.md's
migration notes for why) and never for anything other than passwords.
Refresh tokens are hashed with SHA-256 instead (app/security/tokens.py,
added alongside the auth endpoints) — they're already high-entropy random
values, not something an attacker brute-forces offline the way a human
password is, so Argon2's deliberate slowness buys nothing there and would
only add needless latency to every /auth/refresh call.
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
