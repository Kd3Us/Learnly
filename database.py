"""SQLAlchemy engine, session management, and DB initialisation."""
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models import Base


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Add it as a root-level key in your Streamlit secrets."
    )


def _build_engine():
    return create_engine(
        _get_database_url(),
        echo=(os.environ.get("APP_ENV") == "development"),
        pool_pre_ping=True,
    )


def init_db() -> None:
    """Create all tables. Safe to call multiple times (idempotent).
    
    Must be called inside a Streamlit execution context (inside a function
    or decorated with @st.cache_resource), never at module level.
    """
    engine = _build_engine()
    Base.metadata.create_all(bind=engine)
    engine.dispose()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session, committing on success and rolling back on error.

    Usage:
        with get_db() as db:
            db.add(some_object)
    """
    engine = _build_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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