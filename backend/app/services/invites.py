"""Invite generation and redemption — entirely backend-mediated, both
directions. firestore.rules denies all client access to invites/, so this
module is the only way a code is ever minted, checked, or consumed.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from firebase_admin import firestore as firebase_firestore

CODE_BYTES = 16  # secrets.token_urlsafe(16) -> 128 bits of entropy, not guessable
EXPIRY = timedelta(hours=24)
GENERATION_LIMIT_PER_CASE = 5
GENERATION_WINDOW = timedelta(hours=1)


def _hash_code(code: str) -> str:
    # Never store the raw code outside the invites/ doc itself — the
    # attempt log exists to answer "was this used, by whom", not to hold
    # a second copy of a still-possibly-valid bearer secret.
    return hashlib.sha256(code.encode()).hexdigest()


def _log_attempt(db, *, code: str, case_id: str | None, uid: str, outcome: str) -> None:
    db.collection("inviteAttempts").document().set(
        {
            "codeHash": _hash_code(code),
            "caseId": case_id,
            "attemptedBy": uid,
            "attemptedAt": firebase_firestore.SERVER_TIMESTAMP,
            "outcome": outcome,
        }
    )


def generate_invite(db, case_id: str, created_by: str) -> tuple[str, datetime]:
    """Mints a single-use, 24-hour invite code for a case. Rate-limited
    per case, not per user — codes are the weakest link here (shared over
    WhatsApp, readable by anyone who sees the chat), so capping both how
    long one stays valid and how many a case can mint in a window limits
    how much damage a single leak, or a compromised manager account, can
    do.
    """
    invites_ref = db.collection("invites")
    window_start = datetime.now(timezone.utc) - GENERATION_WINDOW
    recent = 0
    for snap in invites_ref.where("caseId", "==", case_id).stream():
        created_at = (snap.to_dict() or {}).get("createdAt")
        if created_at is not None and created_at >= window_start:
            recent += 1
    if recent >= GENERATION_LIMIT_PER_CASE:
        raise HTTPException(
            status_code=429,
            detail="Too many invite codes generated for this case recently. Try again later.",
        )

    code = secrets.token_urlsafe(CODE_BYTES)
    expires_at = datetime.now(timezone.utc) + EXPIRY
    invites_ref.document().set(
        {
            "code": code,
            "caseId": case_id,
            "roleToGrant": "family",
            "createdBy": created_by,
            "createdAt": firebase_firestore.SERVER_TIMESTAMP,
            "expiresAt": expires_at,
            "redeemedBy": None,
            "redeemedAt": None,
        }
    )
    return code, expires_at


def redeem_invite(db, code: str, uid: str) -> str:
    """Validates and redeems a code atomically: the lookup, the expiry
    and single-use checks, and the familyUids write all happen inside one
    Firestore transaction, so two concurrent redemption attempts for the
    same code can't both succeed — a naive check-then-write done as two
    separate steps would have exactly that race. Returns the caseId.
    Every attempt is logged regardless of outcome, so a leaked code's
    redemption (successful or not) leaves a trail of who tried it and
    what happened.
    """
    matches = list(db.collection("invites").where("code", "==", code).limit(1).stream())
    if not matches:
        _log_attempt(db, code=code, case_id=None, uid=uid, outcome="not_found")
        raise HTTPException(status_code=404, detail="Invalid invite code")

    invite_ref = matches[0].reference
    transaction = db.transaction()

    @firebase_firestore.transactional
    def _run(transaction):
        snap = invite_ref.get(transaction=transaction)
        invite = snap.to_dict() or {}
        case_id = invite.get("caseId")

        if invite.get("redeemedBy"):
            return "already_redeemed", case_id

        expires_at = invite.get("expiresAt")
        if expires_at is not None and expires_at < datetime.now(timezone.utc):
            return "expired", case_id

        case_ref = db.collection("cases").document(case_id)
        transaction.update(
            invite_ref,
            {"redeemedBy": uid, "redeemedAt": firebase_firestore.SERVER_TIMESTAMP},
        )
        transaction.update(case_ref, {"familyUids": firebase_firestore.ArrayUnion([uid])})
        return "redeemed", case_id

    outcome, case_id = _run(transaction)
    _log_attempt(db, code=code, case_id=case_id, uid=uid, outcome=outcome)

    if outcome == "already_redeemed":
        raise HTTPException(status_code=409, detail="This invite code has already been used")
    if outcome == "expired":
        raise HTTPException(status_code=410, detail="This invite code has expired")
    return case_id
