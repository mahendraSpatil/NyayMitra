"""NyayMitra AI FastAPI service.

Owns everything the Flutter client should not: OCR, model calls,
retrieval, verification. The client never calls Gemini or any model
provider directly, and no API key ever ships in the Flutter bundle.
"""

from fastapi import FastAPI

from .auth import install_auth_middleware
from .routers import auth, cases, chat, documents, invites
from .routers.v2 import cases as v2_cases
from .routers.v2 import chat as v2_chat
from .routers.v2 import documents as v2_documents
from .routers.v2 import hearings as v2_hearings
from .routers.v2 import invites as v2_invites
from .routers.v2 import tasks as v2_tasks

app = FastAPI(title="NyayMitra AI Service")

install_auth_middleware(app)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


# Legacy Firebase-authenticated routes — untouched, still serving the
# current Flutter app exactly as before. Deleted in step 6 of the
# Postgres migration (NyayMitra.md), once step 5 has switched the client
# over to /api/v2.
app.include_router(auth.router, prefix="/api/v2")
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(cases.router)
app.include_router(invites.router)

# The Postgres/JWT replacements, built alongside the legacy routes above
# rather than in place of them — nothing switches over to these until
# step 5. Every route here uses one of the authorization dependencies in
# app/dependencies.py; app/security/route_coverage.py enforces that for
# the whole app from this commit on, /api/v2 included.
app.include_router(v2_cases.router, prefix="/api/v2")
app.include_router(v2_hearings.router, prefix="/api/v2")
app.include_router(v2_documents.router, prefix="/api/v2")
app.include_router(v2_chat.router, prefix="/api/v2")
app.include_router(v2_invites.router, prefix="/api/v2")
app.include_router(v2_tasks.router, prefix="/api/v2")
