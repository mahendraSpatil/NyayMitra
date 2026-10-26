"""Loads backend/.env once at import time. Never hardcode a secret here —
this module only reads from the environment."""

import os

from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()


class Settings:
    cloudinary_cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    cloudinary_api_key = os.environ.get("CLOUDINARY_API_KEY", "")
    cloudinary_api_secret = os.environ.get("CLOUDINARY_API_SECRET", "")
    # postgresql+psycopg://... — same var name Neon expects, so prod is
    # just a different value here. Local dev points at a Postgres running
    # in Docker (see .env's comment for the exact command/port).
    database_url = os.environ.get("DATABASE_URL", "")
    # Signs access + refresh tokens. A real secret — see app/security/tokens.py.
    jwt_secret = os.environ.get("JWT_SECRET", "")
    # Comma-separated, no wildcard — see app/main.py's CORSMiddleware setup
    # for why "*" is never valid here (we send credentials; a wildcard
    # origin combined with allow_credentials is both spec-invalid and
    # unsafe). Defaults to the fixed dev port this project's README tells
    # you to run `flutter run -d chrome --web-port=5000` on.
    _cors_origins_raw = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5000")
    cors_allowed_origins = [origin.strip() for origin in _cors_origins_raw.split(",") if origin.strip()]
    # Dev convenience, off by default: `flutter run -d chrome` picks a
    # random port every run unless --web-port is pinned, which makes a
    # fixed CORS_ALLOWED_ORIGINS list fragile while iterating locally.
    # When this is "true", app/main.py additionally allows any
    # http://localhost:<port> origin via regex — deliberately a separate
    # opt-in from CORS_ALLOWED_ORIGINS, not folded into it, so a deployed
    # config can never end up with this on by accident just because
    # CORS_ALLOWED_ORIGINS was copied from a dev .env. Must stay unset (or
    # "false") in any deployed environment: it would let any local process
    # on the same machine as a visitor's browser — not just the Flutter
    # dev server — send this backend credentialed cross-origin requests.
    cors_allow_localhost_regex = os.environ.get("CORS_ALLOW_LOCALHOST_REGEX", "false").lower() == "true"

    # /chat's model backend — see app/llm/. "local" (default) talks to a
    # llama-server instance this machine runs itself; "gemini" is a stub
    # (app/llm/gemini.py) until a real integration exists. Never a
    # fallback between the two at request time — get_llm() picks exactly
    # one provider for the life of the process, per README_chat.md's
    # "no silent fallback" rule.
    llm_provider = os.environ.get("LLM_PROVIDER", "local")
    llm_base_url = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8080")
    llm_model_name = os.environ.get("LLM_MODEL_NAME", "nyaymitra-demo")
    llm_timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "120"))
    llm_max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "400"))
    llm_temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
    # Some chat templates reject a separate system role — set this if
    # llama-server errors on alternating-role/system-message validation.
    llm_merge_system = os.environ.get("LLM_MERGE_SYSTEM", "false").lower() == "true"
    # Sent as the OpenAI-compatible "stop" array in LocalLlamaProvider's
    # payload — without it, the local model was observed inventing and
    # answering its own follow-up "QUESTION:" blocks, with chat-template
    # control tokens (<|im_end|>, <|im_start|>assistant) leaking into the
    # text, instead of stopping after one answer (finish_reason: "length"
    # instead of "stop"). An empty LLM_STOP sends no stop array at all —
    # not the same as an empty list silently keeping the default; a
    # deliberate override to test whether llama-server's own defaults
    # handle it.
    _llm_stop_raw = os.environ.get("LLM_STOP", "<|im_end|>,<|im_start|>,QUESTION:")
    llm_stop = (
        [part.strip() for part in _llm_stop_raw.split(",") if part.strip()] if _llm_stop_raw else []
    )
    max_excerpt_chars = int(os.environ.get("MAX_EXCERPT_CHARS", "6000"))
    # Not read anywhere yet — GeminiProvider is a stub (app/llm/gemini.py)
    # until a real integration exists. Kept here, not scattered, so
    # wiring one in later is a one-file change.
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    gemini_model = os.environ.get("GEMINI_MODEL", "")

    def require_cloudinary(self) -> None:
        if not (self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Cloudinary credentials are not set on the server. Copy "
                    "backend/.env.example to backend/.env and fill in "
                    "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and "
                    "CLOUDINARY_API_SECRET."
                ),
            )


settings = Settings()
