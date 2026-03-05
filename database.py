"""SQLAlchemy engine, session management, and DB initialisation."""
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models import Base

_engine = None
_SessionLocal = None


def _resolve_database_url() -> str:
    """
    Resolve DATABASE_URL at call time, not at import time.

    Priority:
      1. DATABASE_URL environment variable
      2. st.secrets direct read (Streamlit Cloud)

    Raises RuntimeError if no URL is found — a missing DATABASE_URL
    should be a loud, explicit failure rather than a silent fallback.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL") or st.secrets.get("database_url")
        if url:
            return url
    except Exception:
        pass

    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Add it to your Streamlit secrets or environment variables."
    )


def _get_engine():
    """Initialise the engine and session factory on first call."""
    global _engine, _SessionLocal
    if _engine is None:
        from config import settings
        database_url = _resolve_database_url()
        _engine = create_engine(
            database_url,
            echo=(settings.app_env == "development"),
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine, _SessionLocal


def init_db() -> None:
    """Create all tables. Safe to call multiple times (idempotent)."""
    engine, _ = _get_engine()
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session, committing on success and rolling back on error.

    Usage:
        with get_db() as db:
            db.add(some_object)
    """
    _, SessionLocal = _get_engine()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()