"""Database engine, session management and declarative base."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


def _create_engine():
    connect_args = {}
    if settings.is_sqlite:
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _record) -> None:
    if settings.is_sqlite:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_alive(session: Session) -> bool:
    try:
        session.execute(select(1))
        return True
    except Exception:
        logger.exception("event=database_health_check_failed")
        return False
