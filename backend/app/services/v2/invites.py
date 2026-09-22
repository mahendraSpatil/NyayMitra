"""Invite generation and redemption on Postgres — the replacement for
the deleted Firestore-transaction version. Entirely backend-mediated,
both directions; there is no client write path to invites/invite_attempts
in this schema at all (no rules to deny — the tables are simply never
exposed to anything but this module).
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db.models import CaseMember, Invite, InviteAttempt

CODE_BYTES = 16  # secrets.token_urlsafe(16) -> 128 bits of entropy, not guessable
EXPIRY = timedelta(hours=24)
GENERATION_LIMIT_PER_CASE = 5
GENERATION_WINDOW = timedelta(hours=1)


def _hash_code(code: str) -> str:
    # Never store the raw code outside the invites row itself — the
    # attempt log exists to answer "was this used, by whom", not to hold
    # a second copy of a still-possibly-valid bearer secret.
    return hashlib.sha256(code.encode()).hexdigest()


def _log_attempt(db: Session, *, code: str, case_id: uuid.UUID | None, uid: uuid.UUID, outcome: str) -> None:
    db.add(
        InviteAttempt(
            case_id=case_id,
            code_hash=_hash_code(code),
            attempted_by=uid,
            outcome=outcome,
        )
    )


def generate_invite(db: Session, case_id: uuid.UUID, created_by: uuid.UUID) -> tuple[str, datetime]:
    """Mints a single-use, 24-hour invite code for a case. Rate-limited
    per case, not per user — codes are the weakest link here (shared over
    WhatsApp, readable by anyone who sees the chat), so capping both how
    long one stays valid and how many a case can mint in a window limits
    how much damage a single leak, or a compromised manager account, can
    do.
    """
    window_start = datetime.now(timezone.utc) - GENERATION_WINDOW
    count = db.scalar(
        select(func.count())
        .select_from(Invite)
        .where(Invite.case_id == case_id, Invite.created_at >= window_start)
    )
    if count >= GENERATION_LIMIT_PER_CASE:
        raise HTTPException(
            status_code=429,
            detail="Too many invite codes generated for this case recently. Try again later.",
        )

    code = secrets.token_urlsafe(CODE_BYTES)
    expires_at = datetime.now(timezone.utc) + EXPIRY
    db.add(
        Invite(
            case_id=case_id,
            code=code,
            role_to_grant="family",
            created_by=created_by,
            expires_at=expires_at,
        )
    )
    db.commit()
    return code, expires_at


def redeem_invite(db: Session, code: str, uid: uuid.UUID) -> uuid.UUID:
    """Validates and redeems a code atomically: SELECT ... FOR UPDATE
    locks the invite row for the rest of this transaction, so a second
    concurrent redemption attempt for the same code blocks until this one
    commits — then sees the row already redeemed and is correctly
    rejected, rather than both requests reading "not yet redeemed" before
    either writes (the race a naive check-then-write would have). Every
    attempt is logged regardless of outcome, so a leaked code's
    redemption (successful or not) leaves a trail of who tried it and
    what happened.
    """
    invite = db.scalar(select(Invite).where(Invite.code == code).with_for_update())

    if invite is None:
        _log_attempt(db, code=code, case_id=None, uid=uid, outcome="not_found")
        db.commit()
        raise HTTPException(status_code=404, detail="Invalid invite code")

    case_id = invite.case_id

    if invite.redeemed_by is not None:
        _log_attempt(db, code=code, case_id=case_id, uid=uid, outcome="already_redeemed")
        db.commit()
        raise HTTPException(status_code=409, detail="This invite code has already been used")

    if invite.expires_at < datetime.now(timezone.utc):
        _log_attempt(db, code=code, case_id=case_id, uid=uid, outcome="expired")
        db.commit()
        raise HTTPException(status_code=410, detail="This invite code has expired")

    invite.redeemed_by = uid
    invite.redeemed_at = datetime.now(timezone.utc)

    existing_member = db.get(CaseMember, {"case_id": case_id, "user_id": uid})
    if existing_member is None:
        db.add(CaseMember(case_id=case_id, user_id=uid, role="family", is_manager=False))

    _log_attempt(db, code=code, case_id=case_id, uid=uid, outcome="redeemed")
    db.commit()
    return case_id
