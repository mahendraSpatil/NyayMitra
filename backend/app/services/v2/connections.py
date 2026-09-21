"""In-process WebSocket connection registry and broadcaster. One process,
no external pub/sub — fine at this scale (see NyayMitra.md); the moment
this backend runs as more than one worker, broadcasts stop reaching
every subscriber and this needs a real message bus instead.

Two channels (app/routers/v2/ws.py):
  - cases/{caseId}: everyone currently subscribed to a case, regardless
    of who they are — hearings/documents/etc. changing on a case a user
    can see.
  - me: one user's own cross-case lists (docket, task list, case list)
    — things scoped to a user, not a single case.

HTTP route handlers that write data are synchronous (SQLAlchemy's sync
session, not an async driver) and run in FastAPI's worker thread pool,
not on the event loop — so they can't just `await` a broadcast. The
_sync wrappers below hand the coroutine to the event loop via
run_coroutine_threadsafe instead, fire-and-forget: a broadcast failing
(a dead socket, a slow client) must never fail the HTTP request that
triggered it. bind_loop() is called once from main.py's lifespan
startup, before any request can arrive.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger("nyaymitra.ws")


@dataclass
class _Registry:
    # case_id -> user_id -> that user's live sockets on this case's channel.
    # Keyed by user too (not just a flat set) so a specific user's case
    # sockets can be closed on their own — e.g. once case-member removal
    # exists as a feature, without touching any other subscriber.
    case_subscribers: dict[uuid.UUID, dict[uuid.UUID, set[WebSocket]]] = field(default_factory=dict)
    user_subscribers: dict[uuid.UUID, set[WebSocket]] = field(default_factory=dict)


class ConnectionManager:
    def __init__(self) -> None:
        self._registry = _Registry()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # --- subscribe / unsubscribe: plain dict mutation, no I/O, no await
    # needed and therefore no risk of another coroutine interleaving
    # mid-update on this single-threaded event loop. ---

    def subscribe_case(self, case_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        by_user = self._registry.case_subscribers.setdefault(case_id, {})
        by_user.setdefault(user_id, set()).add(websocket)

    def unsubscribe_case(self, case_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        by_user = self._registry.case_subscribers.get(case_id)
        if not by_user:
            return
        sockets = by_user.get(user_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                del by_user[user_id]
        if not by_user:
            del self._registry.case_subscribers[case_id]

    def subscribe_user(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        self._registry.user_subscribers.setdefault(user_id, set()).add(websocket)

    def unsubscribe_user(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        sockets = self._registry.user_subscribers.get(user_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            del self._registry.user_subscribers[user_id]

    # --- broadcast: invalidations only, e.g. {"type": "hearings_changed",
    # "caseId": "..."} — never the changed data itself. The receiving
    # client refetches through the normal authorized REST endpoint, so a
    # socket is never a second way to read case contents, only a signal
    # to go re-read the first one. ---

    async def broadcast_case(self, case_id: uuid.UUID, message: dict) -> None:
        by_user = self._registry.case_subscribers.get(case_id)
        if not by_user:
            return
        for sockets in list(by_user.values()):
            await self._send_to_all(sockets, message)

    async def broadcast_user(self, user_id: uuid.UUID, message: dict) -> None:
        sockets = self._registry.user_subscribers.get(user_id)
        if not sockets:
            return
        await self._send_to_all(sockets, message)

    async def close_case_sockets_for_user(self, case_id: uuid.UUID, user_id: uuid.UUID, *, code: int) -> None:
        """No current endpoint removes a case_member row — there is no
        "remove someone from a case" feature yet — so nothing calls this
        in production today. It exists because the plan asked for the
        capability regardless, and it's exercised directly by
        tests/v2/test_ws.py rather than through a real removal endpoint
        that doesn't exist yet.
        """
        by_user = self._registry.case_subscribers.get(case_id)
        if not by_user:
            return
        sockets = by_user.pop(user_id, set())
        if not by_user:
            self._registry.case_subscribers.pop(case_id, None)
        for websocket in sockets:
            await _safe_close(websocket, code=code)

    async def _send_to_all(self, sockets: set[WebSocket], message: dict) -> None:
        dead: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            sockets.discard(websocket)

    # --- sync wrappers for HTTP route handlers (thread-pool, not the
    # event loop) to call after db.commit(). ---

    def broadcast_case_sync(self, case_id: uuid.UUID, message: dict) -> None:
        self._schedule(self.broadcast_case(case_id, message))

    def broadcast_user_sync(self, user_id: uuid.UUID, message: dict) -> None:
        self._schedule(self.broadcast_user(user_id, message))

    def _schedule(self, coro) -> None:
        if self._loop is None:
            logger.warning("ConnectionManager used before bind_loop() — dropping broadcast")
            coro.close()
            return
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        future.add_done_callback(_log_broadcast_errors)


def _log_broadcast_errors(future: "asyncio.Future") -> None:
    exc = future.exception()
    if exc is not None:
        logger.warning("broadcast failed: %r", exc)


async def _safe_close(websocket: WebSocket, *, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        pass  # already disconnected — closing an already-closed socket is a no-op, not an error


manager = ConnectionManager()
