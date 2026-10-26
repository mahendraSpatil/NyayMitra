"""The authorization boundary for the app. firestore.rules no longer
exists (step 6 of the Firebase migration — see NyayMitra.md) — these
dependencies ARE the security boundary, not a convenience layer in front
of one. Every dependency here ultimately resolves through
get_current_user, which is exactly what tests/test_route_coverage.py
checks for: a route with none of these anywhere in its dependency tree
is unprotected, full stop.

Three shapes, because case/resource identifiers show up three different
ways across the routes that need them:
  - in the URL path (require_case_member / require_case_manager)
  - in the JSON body (require_case_member_from_body — /chat,
    sign-upload, confirm-upload all take caseId as a body field, not a
    path segment)
  - via another resource entirely (require_task_owner — /tasks/{id}/...
    has no caseId at all; ownership is the task's own assigned_to_uid)
"""

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db.base import get_db
from .db.models import CaseMember, Task
from .security.tokens import decode_access_token


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    role: str


def get_current_user(request: Request) -> CurrentUser:
    header = request.headers.get("authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = header.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Access token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid access token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Malformed access token")

    return CurrentUser(id=user_id, role=payload.get("role", ""))


def _member_or_403(db: Session, case_id: uuid.UUID, user: CurrentUser) -> CaseMember:
    member = db.get(CaseMember, {"case_id": case_id, "user_id": user.id})
    if member is None:
        raise HTTPException(status_code=403, detail="Not authorized for this case")
    return member


def require_case_member(
    case_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """For routes with {case_id} (or {caseId} — FastAPI matches the path
    param by name, so the route's path parameter must be spelled
    case_id) in their URL path.
    """
    _member_or_403(db, case_id, current_user)
    return current_user


def require_case_manager(
    case_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUser:
    member = _member_or_403(db, case_id, current_user)
    if not member.is_manager:
        raise HTTPException(status_code=403, detail="Not a manager of this case")
    return current_user


def require_case_reviewer(
    case_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Who may confirm/correct a key field read from a document (dates,
    sections, FIR numbers): the advocate or NGO on the case, or a case
    manager (a family that created its own case, with nobody else to
    ask). A family member who merely joined by invite may not — they can
    see what needs checking, but the confirmation is a professional's or
    the case owner's call. The reviewer's role is recorded on the field.
    """
    member = _member_or_403(db, case_id, current_user)
    if member.role not in ("advocate", "ngo") and not member.is_manager:
        raise HTTPException(
            status_code=403, detail="Only the advocate, NGO, or case manager can confirm document facts"
        )
    return current_user


def require_case_member_from_body(body_field: str = "caseId", *, optional: bool = False):
    """Factory, not a bare dependency: /chat, /documents/sign-upload, and
    /documents/confirm-upload all take their case id as a JSON body
    field rather than a path segment, so there's no {case_id} for
    FastAPI's normal path-param resolution to hand us. Reads the body
    directly off the request instead — still a real Depends(), still
    discoverable by the route-coverage test, just sourced differently.

    optional=True is /chat's case: caseId is allowed to be entirely
    absent (the chatbot FAB is portal-home-level for Advocate/NGO, with
    no single case in scope), in which case this only requires a valid
    signed-in user and skips the membership check — there is no case to
    check membership against. It is never optional for sign-upload /
    confirm-upload, which always need a real case to attach the document
    to.
    """

    async def _dependency(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> CurrentUser:
        try:
            body = await request.json()
        except Exception:
            body = {}

        raw_case_id = body.get(body_field)
        if raw_case_id is None:
            if optional:
                return current_user
            raise HTTPException(status_code=422, detail=f"Missing '{body_field}' in request body")

        try:
            case_id = uuid.UUID(raw_case_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=f"'{body_field}' is not a valid case id")

        _member_or_403(db, case_id, current_user)
        return current_user

    return _dependency


def require_task_owner(
    task_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """For /tasks/{task_id}/... — there's no caseId here at all;
    authorization is the task's own assigned_to_uid.
    """
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.assigned_to_uid != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this task")
    return current_user
