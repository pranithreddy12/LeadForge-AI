from __future__ import annotations

from contextlib import contextmanager

from app.core.database import SessionLocal


@contextmanager
def task_session():
    """Per-task DB session — workers don't use FastAPI's get_db."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
