"""NyayMitra AI FastAPI service.

Owns everything the Flutter client should not: OCR, model calls,
retrieval, verification. The client never calls Gemini or any model
provider directly, and no API key ever ships in the Flutter bundle.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .llm.base import LLMProvider
from .llm.factory import get_llm
from .routers import auth
from .routers.v2 import case_events as v2_case_events
from .routers.v2 import cases as v2_cases
from .routers.v2 import chat as v2_chat
from .routers.v2 import documents as v2_documents
from .routers.v2 import hearings as v2_hearings
from .routers.v2 import invites as v2_invites
from .routers.v2 import tasks as v2_tasks
from .routers.v2 import ws as v2_ws
from .services.v2.connections import manager as ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The WS connection manager broadcasts from HTTP route handlers,
    # which run in FastAPI's worker thread pool, not on the event loop —
    # it needs a reference to the loop to hand broadcasts back to via
    # run_coroutine_threadsafe. Must happen before any request can arrive.
    ws_manager.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="NyayMitra AI Service", lifespan=lifespan)

# Without this, a browser's preflight OPTIONS to any /api/v2 route gets a
# plain 405 (Starlette's router has no OPTIONS handler registered unless
# something adds one) and the browser never sends the real request at
# all — the actual bug behind "login works from curl but not from the
# Flutter web build," where curl simply never preflights.
#
# allow_origins is never "*": this app sends credentials (the Bearer
# access token / the refresh token in the body — either way,
# allow_credentials=True below), and a wildcard origin combined with
# credentials is both invalid per the CORS spec (browsers reject it
# outright) and unsafe if it somehow weren't. CORS_ALLOWED_ORIGINS
# (app/config.py) is the explicit, comma-separated allowlist; only
# CORS_ALLOW_LOCALHOST_REGEX (off by default, dev-only, see config.py's
# comment on it) adds any flexibility beyond that literal list — this
# app.add_middleware call never allows a bare "*" regex either.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_origin_regex=r"http://localhost:\d+" if settings.cors_allow_localhost_regex else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", tags=["health"])
async def health(llm: LLMProvider = Depends(get_llm)) -> dict:
    # llm.health() makes a real (short-timeout) network call to whatever
    # LLM_PROVIDER points at — this endpoint is no longer purely
    # in-process. Nothing else in this app currently depends on /health
    # being instant (no liveness probe wired up), so that tradeoff is
    # accepted rather than worked around with a second endpoint.
    return {"status": "ok", "llm": await llm.health(), "llmProvider": llm.name}


# Every route in the app now lives under /api/v2 and is authorized by
# one of the dependencies in app/dependencies.py — Firebase, its ID-token
# middleware, and the pre-Postgres routers they used to gate are gone
# (step 6 of the migration; see NyayMitra.md). app/security/route_coverage.py
# enforces that every route here (auth.router's /auth/login and
# /auth/refresh excepted, and /health) carries real authorization, not
# developer discipline.
app.include_router(auth.router, prefix="/api/v2")
app.include_router(v2_cases.router, prefix="/api/v2")
app.include_router(v2_hearings.router, prefix="/api/v2")
app.include_router(v2_case_events.router, prefix="/api/v2")
app.include_router(v2_documents.router, prefix="/api/v2")
app.include_router(v2_chat.router, prefix="/api/v2")
app.include_router(v2_invites.router, prefix="/api/v2")
app.include_router(v2_tasks.router, prefix="/api/v2")
app.include_router(v2_ws.router, prefix="/api/v2")
