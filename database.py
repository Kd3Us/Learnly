"""SQLAlchemy engine, session management, and DB initialisation."""
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models import Base


def _get_database_url() -> str:
    """
    Read DATABASE_URL at call time directly from os.environ.

    Streamlit Cloud automatically injects root-level secrets as environment
    variables before any page code runs, so os.environ is the most reliable
    source — no singleton, no lazy cache, no st.secrets workaround needed.

    Raises RuntimeError if DATABASE_URL is not set.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Add it as a root-level key in your Streamlit secrets or "
        "as an environment variable."
    )


def _make_engine():
    url = _get_database_url()
    return create_engine(url, echo=(os.environ.get("APP_ENV") == "development"))


def _make_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables. Safe to call multiple times (idempotent)."""
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session, committing on success and rolling back on error.

    Usage:
        with get_db() as db:
            db.add(some_object)
    """
    engine = _make_engine()
    SessionLocal = _make_session_factory(engine)
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        engine.dispose()