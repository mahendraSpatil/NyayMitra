"""Firebase ID token verification, applied to every request via ASGI
middleware — not a per-route dependency, so a router added later without
remembering to wire it in is still covered; this runs before routing even
resolves which endpoint handles the request.
"""

import os

import firebase_admin
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin import firestore as firebase_firestore

PROJECT_ID = "nyaymitra-ai-92fcc"

# Named Firestore database (Enterprise edition), not the classic single
# database literally named "(default)". Every Firestore client in this
# backend must target this explicitly — seed.py already does, and the
# Flutter client was silently querying the wrong (empty) database for a
# while before that was caught. Not repeating that mistake here.
FIRESTORE_DATABASE_ID = "default"

_firebase_app: firebase_admin.App | None = None
_firestore_db = None


def get_firebase_app() -> firebase_admin.App:
    global _firebase_app
    if _firebase_app is None:
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            raise RuntimeError(
                "GOOGLE_APPLICATION_CREDENTIALS is not set. Point it at a "
                "service account key outside this repo before handling "
                "authenticated requests."
            )
        _firebase_app = firebase_admin.initialize_app(
            credentials.ApplicationDefault(), {"projectId": PROJECT_ID}
        )
    return _firebase_app


def get_firestore_db():
    global _firestore_db
    if _firestore_db is None:
        _firestore_db = firebase_firestore.client(
            app=get_firebase_app(), database_id=FIRESTORE_DATABASE_ID
        )
    return _firestore_db


def install_auth_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def verify_firebase_token(request: Request, call_next):
        header = request.headers.get("authorization")
        if not header or not header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
            )

        token = header.removeprefix("Bearer ").strip()
        try:
            decoded = firebase_auth.verify_id_token(token, app=get_firebase_app())
        except Exception as exc:  # any verification failure is a 401, not a 500
            return JSONResponse(
                status_code=401,
                content={"detail": f"Invalid or expired token: {exc}"},
            )

        request.state.user = decoded
        return await call_next(request)
