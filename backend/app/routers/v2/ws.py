"""Two invalidation channels — see app/services/v2/connections.py for the
registry/broadcast mechanics and app/security/ws_auth.py for why auth
here is a first-message handshake rather than a FastAPI Depends().
Neither route ever sends case/task/user data over the socket, only a
{"type": ...} invalidation the client reacts to by refetching through the
REST endpoints it already has (and is already authorized to call) —
these sockets are not a second read path.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from ...db.base import get_db
from ...db.models import CaseMember
from ...security.ws_auth import (
    CLOSE_NOT_AUTHORIZED,
    CLOSE_TOKEN_EXPIRED,
    authenticate_websocket,
    websocket_authenticated,
)
from ...services.v2.connections import manager

router = APIRouter()


async def _close_when_expired(websocket: WebSocket, expires_at) -> None:
    delay = (expires_at - datetime.now(timezone.utc)).total_seconds()
    await asyncio.sleep(max(delay, 0))
    try:
        await websocket.close(code=CLOSE_TOKEN_EXPIRED)
    except Exception:
        pass  # already disconnected — not an error


@router.websocket("/ws/cases/{case_id}")
@websocket_authenticated
async def case_socket(websocket: WebSocket, case_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    auth = await authenticate_websocket(websocket)
    if auth is None:
        return

    member = db.get(CaseMember, {"case_id": case_id, "user_id": auth.user.id})
    if member is None:
        await websocket.close(code=CLOSE_NOT_AUTHORIZED)
        return

    manager.subscribe_case(case_id, auth.user.id, websocket)
    expiry_task = asyncio.create_task(_close_when_expired(websocket, auth.expires_at))
    try:
        while True:
            # Nothing meaningful for a client to send here — this
            # channel is server-to-client only — but a receive loop is
            # what turns a WebSocketDisconnect into something we can
            # catch to clean up on, instead of leaking the subscription.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        expiry_task.cancel()
        manager.unsubscribe_case(case_id, auth.user.id, websocket)


@router.websocket("/ws/me")
@websocket_authenticated
async def me_socket(websocket: WebSocket) -> None:
    auth = await authenticate_websocket(websocket)
    if auth is None:
        return

    manager.subscribe_user(auth.user.id, websocket)
    expiry_task = asyncio.create_task(_close_when_expired(websocket, auth.expires_at))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        expiry_task.cancel()
        manager.unsubscribe_user(auth.user.id, websocket)
