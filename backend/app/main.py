"""NyayMitra AI FastAPI service.

Owns everything the Flutter client should not: OCR, model calls,
retrieval, verification. The client never calls Gemini or any model
provider directly, and no API key ever ships in the Flutter bundle.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .routers import auth
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


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


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
app.include_router(v2_documents.router, prefix="/api/v2")
app.include_router(v2_chat.router, prefix="/api/v2")
app.include_router(v2_invites.router, prefix="/api/v2")
app.include_router(v2_tasks.router, prefix="/api/v2")
app.include_router(v2_ws.router, prefix="/api/v2")
