"""Postgres engine/session setup. The backend's only datastore, as of
step 6 of the Firebase migration (see NyayMitra.md) — Firestore is gone.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    if not settings.database_url:
        return None
    return create_engine(settings.database_url, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency — one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
