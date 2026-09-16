"""NyayMitra AI FastAPI service.

Owns everything the Flutter client should not: OCR, model calls,
retrieval, verification. The client never calls Gemini or any model
provider directly, and no API key ever ships in the Flutter bundle.
"""

from fastapi import FastAPI

from .auth import install_auth_middleware
from .routers import cases, chat, documents

app = FastAPI(title="NyayMitra AI Service")

install_auth_middleware(app)

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(cases.router)
