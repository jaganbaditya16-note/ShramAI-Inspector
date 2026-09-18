"""Test configuration.

Environment is pinned BEFORE the app is imported so cached settings pick up
test values: inline pipeline (deterministic), isolated sqlite database and
storage, rate limiting off by default.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="shramai-tests-"))

os.environ.update(
    APP_ENV="local",
    AUTH_MODE="demo",
    PIPELINE_MODE="inline",
    DATABASE_URL=f"sqlite:///{_tmp/'test.db'}",
    STORAGE_DIR=str(_tmp / "storage"),
    RATE_LIMIT_ENABLED="false",
    LOG_LEVEL="WARNING",
    KNOWLEDGE_DIR="",
    OLLAMA_MODEL="",
)

import pytest  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.storage import reset_store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

TABLES = [
    "audit_events", "reports", "model_runs", "findings", "processing_jobs",
    "documents", "cases", "auth_sessions", "users", "organizations",
]


@pytest.fixture(autouse=True)
def clean_state():
    """Fresh database + storage + limiter state for every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    limiter.reset()
    reset_store()
    yield
    reset_store()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db() -> SessionLocal:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_demo(client) -> dict:
    """App startup seeds the demo workspace; return its ids."""
    with SessionLocal() as session:
        org = session.execute(text("SELECT id FROM organizations LIMIT 1")).scalar_one()
        case = session.execute(text("SELECT id FROM cases LIMIT 1")).scalar_one()
        document = session.execute(text("SELECT id FROM documents LIMIT 1")).scalar_one()
    return {"org_id": org, "case_id": case, "document_id": document}
