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

PROJECT_ID = "nyaymitra-ai-92fcc"

_firebase_app: firebase_admin.App | None = None


def _get_firebase_app() -> firebase_admin.App:
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
            decoded = firebase_auth.verify_id_token(token, app=_get_firebase_app())
        except Exception as exc:  # any verification failure is a 401, not a 500
            return JSONResponse(
                status_code=401,
                content={"detail": f"Invalid or expired token: {exc}"},
            )

        request.state.user = decoded
        return await call_next(request)
