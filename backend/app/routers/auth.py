import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.base import get_db
from ..db.models import RefreshToken, User
from ..dependencies import CurrentUser, get_current_user
from ..models.auth import LoginRequest, LogoutRequest, MeResponse, RefreshRequest, TokenResponse
from ..security.passwords import verify_password
from ..security.tokens import (
    REFRESH_TOKEN_TTL,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)

router = APIRouter(tags=["auth"])
logger = logging.getLogger("nyaymitra.auth")


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
        )
    )
    db.commit()
    return TokenResponse(
        accessToken=create_access_token(str(user.id), user.role),
        refreshToken=raw_refresh,
        role=user.role,
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    # Same generic message whether the email doesn't exist or the
    # password is wrong — distinguishing the two tells an attacker which
    # emails are registered.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _issue_tokens(db, user)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token_hash = hash_refresh_token(payload.refreshToken)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if token is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token.replaced_by_id is not None:
        # This exact token was already exchanged for a newer one — the
        # only way to present it again is a copy of it existing
        # somewhere it shouldn't (a stolen token used after the
        # legitimate client already rotated past it). Treat the whole
        # session as compromised, not just this one token.
        revoked_count = (
            db.query(RefreshToken)
            .filter(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
            .update({"revoked_at": datetime.now(timezone.utc)})
        )
        db.commit()
        logger.warning(
            "refresh token reuse detected for user_id=%s — revoked %d token(s)",
            token.user_id,
            revoked_count,
        )
        raise HTTPException(status_code=401, detail="Refresh token has already been used")

    if token.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    if token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired")

    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    raw_refresh = generate_refresh_token()
    new_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
    )
    db.add(new_token)
    db.flush()  # assigns new_token.id
    token.replaced_by_id = new_token.id
    db.commit()

    return TokenResponse(
        accessToken=create_access_token(str(user.id), user.role),
        refreshToken=raw_refresh,
        role=user.role,
    )


@router.post("/auth/logout", status_code=204)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> None:
    token_hash = hash_refresh_token(payload.refreshToken)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    # Logging out with an already-invalid token is a no-op, not an
    # error — the caller's goal (this token stops working) is already
    # true.
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(timezone.utc)
        db.commit()


@router.get("/me", response_model=MeResponse)
def me(
    current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> MeResponse:
    user = db.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        displayName=user.display_name,
        phone=user.phone,
        preferredLanguage=user.preferred_language,
    )
