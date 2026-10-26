from typing import Literal

from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        # A pasted email with a trailing space, or one typed in a
        # different case than it was registered with, must not read as
        # "wrong password" — login compares email by exact string
        # equality (see login() below), so without this a perfectly
        # correct password looks identical to a wrong one. Normalized
        # here, not just client-side (client/lib/core/services/auth_service.dart
        # does the same for UX — showing the corrected value before it's
        # even sent) because the server-side check must never depend on
        # the client having bothered to normalize anything.
        return value.strip().lower()


class RegisterRequest(BaseModel):
    email: str
    password: str
    displayName: str
    # Self-declared, unverified — see NyayMitra.md's "Future work: role
    # verification". The Literal type only guarantees the value is one of
    # these three strings, not that the caller actually holds that role.
    role: Literal["advocate", "ngo", "family"]

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        # Same normalization as LoginRequest, applied at registration
        # time so the stored email is already in the exact form login
        # will compare against later — one normalization rule, applied
        # once, rather than "normalize on read" logic duplicated at every
        # future email comparison.
        return value.strip().lower()


class RegisterResponse(BaseModel):
    # Deliberately not a TokenResponse — registration does not sign the
    # caller in. See routers/auth.py's register() for why.
    id: str
    email: str
    role: str


class RefreshRequest(BaseModel):
    refreshToken: str


class LogoutRequest(BaseModel):
    refreshToken: str


class TokenResponse(BaseModel):
    accessToken: str
    refreshToken: str
    role: str


class MeResponse(BaseModel):
    id: str
    email: str
    role: str
    displayName: str
    # Added for step 5 of the Postgres migration: /me becomes the client's
    # only source of "my own profile" (client/lib/core/models/user_profile.dart's
    # UserProfile), replacing the old direct Firestore users/{uid} read —
    # which returned these two fields, so /me has to as well.
    phone: str | None
    preferredLanguage: str | None
