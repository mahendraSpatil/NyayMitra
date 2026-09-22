from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


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
