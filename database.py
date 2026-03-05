"""SQLAlchemy engine, session management, and DB initialisation."""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models import Base

_engine = None
_SessionLocal = None


def _get_engine():
    """Initialise the engine and session factory on first call."""
    global _engine, _SessionLocal
    if _engine is None:
        from config import settings
        _engine = create_engine(
            settings.database_url,
            echo=(settings.app_env == "development"),
            connect_args={"check_same_thread": False} if settings.is_sqlite else {},
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