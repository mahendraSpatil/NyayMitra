"""WebSocket authentication — first-message token handshake, not a URL
param (a token in a WS URL ends up in server logs and browser history the
same way a GET query string does) and not FastAPI's normal per-route
Depends() the way get_current_user works for HTTP.

That's a real, deliberate difference, not an oversight: Depends() for a
WebSocket route resolves from the connection's headers/query/cookies at
handshake time, before the endpoint body runs — there is no hook for
"read the first message the client sends after accept() and validate
that instead". The auth work has to live in the endpoint body, which
means app/security/route_coverage.py's HTTP mechanism (walking a
Dependant tree for get_current_user) literally cannot see it. The
@websocket_authenticated decorator exists to give the coverage checker
something to see instead: it marks a function as having gone through
authenticate_websocket(), which is the only thing that actually performs
the handshake. A WS route without the decorator gets caught the same way
an HTTP route without get_current_user does.
"""

import asyncio
import functools
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from ..dependencies import CurrentUser
from .tokens import decode_access_token

# Long enough for a real client to send its first message right after
# the connection opens; short enough that a connection which never
# authenticates doesn't sit around consuming a slot indefinitely.
HANDSHAKE_TIMEOUT_SECONDS = 5.0

CLOSE_HANDSHAKE_FAILED = 4401  # no token, malformed, or invalid/expired within the timeout
CLOSE_TOKEN_EXPIRED = 4401  # same family of reason — the credential is no longer good
CLOSE_NOT_AUTHORIZED = 4403  # authenticated, but not a member of the case being subscribed to
CLOSE_REMOVED_FROM_CASE = 4403


@dataclass(frozen=True)
class AuthenticatedConnection:
    user: CurrentUser
    expires_at: datetime


def websocket_authenticated(handler):
    """Wraps a WebSocket endpoint so it CANNOT run without a successful
    handshake — this is the enforcing mechanism, not a promise that the
    handler calls authenticate_websocket() itself somewhere in its body.
    The wrapper always calls it first; the wrapped handler only ever runs
    after that succeeds, with the result available as websocket.state.auth
    (an AuthenticatedConnection) — set on Starlette's own per-connection
    .state object, the same pattern app/auth.py already uses for HTTP via
    request.state.user, rather than adding a new parameter to the
    handler's signature that FastAPI's own route introspection wouldn't
    know how to resolve.

    functools.wraps matters here beyond the usual __name__/__doc__
    copying: it sets __wrapped__, which inspect.signature() (what
    FastAPI's route registration actually calls) follows by default — so
    FastAPI still sees the original handler's real parameters (case_id,
    db: Session = Depends(get_db), ...) for routing and dependency
    injection, even though the function actually bound to the route is
    this wrapper.
    """

    @functools.wraps(handler)
    async def wrapper(websocket: WebSocket, *args, **kwargs):
        auth = await authenticate_websocket(websocket)
        if auth is None:
            return  # already closed, with a reason code — nothing left to do
        websocket.state.auth = auth
        return await handler(websocket, *args, **kwargs)

    wrapper.__nyaymitra_ws_authenticated__ = True
    return wrapper


async def authenticate_websocket(
    websocket: WebSocket, *, timeout: float = HANDSHAKE_TIMEOUT_SECONDS
) -> AuthenticatedConnection | None:
    """Accepts the connection, then requires the first message to be
    {"accessToken": "..."} within [timeout] seconds. Returns None (and
    has already closed the socket, with a reason code) on any failure —
    callers just need to check for None and return.
    """
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await _safe_close(websocket, CLOSE_HANDSHAKE_FAILED)
        return None

    try:
        payload = json.loads(raw)
        token = payload["accessToken"]
        claims = decode_access_token(token)
        user_id = uuid.UUID(claims["sub"])
        role = claims.get("role", "")
        expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, jwt.PyJWTError):
        await _safe_close(websocket, CLOSE_HANDSHAKE_FAILED)
        return None

    return AuthenticatedConnection(user=CurrentUser(id=user_id, role=role), expires_at=expires_at)


async def _safe_close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        pass  # already disconnected — not an error
