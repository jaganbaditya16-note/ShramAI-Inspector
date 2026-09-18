"""Step-11 reliability: concurrency and resource-behaviour regressions.

Reproductions for the defects found in the production-readiness review:
- duplicate active processing jobs under concurrent reprocess calls
  (now impossible: partial unique index + IntegrityError -> 409)
- per-row latest-job queries on the documents list (N+1, now batched)

Plus live-server probes for concurrent uploads and reads during processing,
and the 0004 migration's duplicate-job data cleanup.
"""

from __future__ import annotations

import concurrent.futures as cf
import os
import socket
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest
from app.db.session import SessionLocal, engine
from app.models import Document, ProcessingJob
from app.services import pipeline, synthetic
from sqlalchemy import event

PDF = synthetic.build_synthetic_pdf()
NOW = "2026-09-18 12:00:00"


# --- helpers ---------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_healthy(base: str, client: httpx.Client, deadline_s: float = 30) -> None:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            if client.get(f"{base}/api/v1/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise RuntimeError("live server did not become healthy")


def _drain_document(client: httpx.Client, base: str, document_id: str, deadline_s: float = 60) -> str:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        status = client.get(f"{base}/api/v1/documents/{document_id}", timeout=10).json()["status"]
        if status in ("processed", "failed"):
            return status
        time.sleep(0.3)
    raise AssertionError(f"document {document_id} never reached a terminal state")


def _job_rows(db_path: Path, document_id: str) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT status, count(*) FROM processing_jobs WHERE document_id = ? GROUP BY status",
            (document_id,),
        ).fetchall()
        return dict(rows)
    finally:
        conn.close()


@pytest.fixture(scope="module")
def live_background_server(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, Path]:
    """One live API server with the production-default background pipeline."""
    port = _free_port()
    root = tmp_path_factory.mktemp("reliability")
    db_path = root / "rel.db"
    env = {
        **os.environ,
        "APP_ENV": "local",
        "AUTH_MODE": "demo",
        "PIPELINE_MODE": "background",
        "DATABASE_URL": f"sqlite:///{db_path}",
        "STORAGE_DIR": str(root / "storage"),
        "RATE_LIMIT_ENABLED": "false",
        "KNOWLEDGE_DIR": "",
        "OLLAMA_MODEL": "",
    }
    proc = subprocess.Popen(
        [".venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=".",
    )
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=10) as client:
            _wait_healthy(base, client)
        yield base, db_path
    finally:
        proc.terminate()
        proc.wait(timeout=15)


# --- concurrent reprocess: never two active jobs at once ----------------------------


def _job_intervals(db_path: Path, document_id: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT id, started_at, finished_at FROM processing_jobs WHERE document_id = ?"
            " AND started_at IS NOT NULL",
            (document_id,),
        ).fetchall()
    finally:
        conn.close()


def test_concurrent_reprocess_never_runs_two_jobs_at_once(live_background_server):
    """A reprocess burst must never put two jobs into execution simultaneously
    (previously possible: SELECT-then-INSERT race let both run the pipeline,
    interleaving the findings delete-and-rebuild cycle).

    Honest invariants: every response is 202 or 409 (never 5xx); every
    accepted reprocess runs exactly once; execution intervals of the jobs
    never overlap. (A later request may legitimately get 202 after an earlier
    burst job already finished — that is a fresh, sequential job.)"""
    base, db_path = live_background_server
    with httpx.Client(timeout=30) as c:
        case = c.post(f"{base}/api/v1/cases", json={"title": "Concurrent Reprocess"}).json()
        upload = c.post(
            f"{base}/api/v1/cases/{case['id']}/documents",
            files={"file": ("race.pdf", PDF, "application/pdf")},
        ).json()
        document_id = upload["document"]["id"]
        assert _drain_document(c, base, document_id) == "processed"

        barrier = threading.Barrier(8)

        def fire(_: int) -> int:
            barrier.wait()
            return c.post(f"{base}/api/v1/documents/{document_id}/reprocess").status_code

        with cf.ThreadPoolExecutor(8) as pool:
            codes = list(pool.map(fire, range(8)))

        accepted = codes.count(202)
        assert set(codes) <= {202, 409}, f"unexpected statuses: {sorted(set(codes))}"
        assert accepted >= 1
        assert _drain_document(c, base, document_id) == "processed"

        rows = _job_rows(db_path, document_id)
        assert set(rows) <= {"succeeded"}, f"all jobs must succeed cleanly, found {rows}"
        assert sum(rows.values()) == accepted + 1  # initial upload + accepted reprocesses

        # No two jobs were ever in execution at the same time.
        from datetime import datetime

        intervals = [
            (datetime.fromisoformat(started), datetime.fromisoformat(finished or started))
            for _, started, finished in _job_intervals(db_path, document_id)
        ]
        intervals.sort()
        from itertools import pairwise

        for (_, end_a), (start_b, _) in pairwise(intervals):
            assert start_b >= end_a, "two jobs executed concurrently on one document"


def test_concurrent_uploads_stay_consistent(live_background_server):
    """Parallel uploads to one case: every upload succeeds exactly once and
    every document reaches a terminal state with nothing stuck."""
    base, _ = live_background_server
    with httpx.Client(timeout=60) as c:
        case = c.post(f"{base}/api/v1/cases", json={"title": "Concurrent Uploads"}).json()

        start = threading.Barrier(6)

        def upload(index: int) -> int:
            start.wait()
            response = c.post(
                f"{base}/api/v1/cases/{case['id']}/documents",
                files={"file": (f"burst-{index}.pdf", PDF, "application/pdf")},
            )
            return response.status_code

        with cf.ThreadPoolExecutor(6) as pool:
            codes = list(pool.map(upload, range(6)))
        assert codes == [202] * 6

        listing = c.get(f"{base}/api/v1/cases/{case['id']}/documents", params={"limit": 100}).json()
        assert listing["meta"]["total"] == 6
        for item in listing["items"]:
            assert _drain_document(c, base, item["id"]) == "processed"

        listing = c.get(f"{base}/api/v1/cases/{case['id']}/documents", params={"limit": 100}).json()
        assert all(item["status"] == "processed" for item in listing["items"])
        assert not [item for item in listing["items"] if item["job"] and item["job"]["status"] in ("queued", "running")]


def test_reads_during_processing_never_fail(live_background_server):
    """Reads (list/findings/audit) concurrent with background jobs are
    2xx/4xx-safe, never 5xx."""
    base, _ = live_background_server
    with httpx.Client(timeout=30) as c:
        case = c.post(f"{base}/api/v1/cases", json={"title": "Reads Under Load"}).json()
        uploads = [
            c.post(
                f"{base}/api/v1/cases/{case['id']}/documents",
                files={"file": (f"load-{i}.pdf", PDF, "application/pdf")},
            ).json()["document"]["id"]
            for i in range(4)
        ]

        stop = threading.Event()

        def read_loop() -> list[int]:
            codes: list[int] = []
            while not stop.is_set():
                for path in (
                    f"/api/v1/cases/{case['id']}/documents",
                    f"/api/v1/cases/{case['id']}/findings",
                    f"/api/v1/cases/{case['id']}/audit",
                ):
                    codes.append(c.get(base + path, params={"limit": 100}).status_code)
            return codes

        with cf.ThreadPoolExecutor(3) as pool:
            reader = pool.submit(read_loop)
            for document_id in uploads:
                _drain_document(c, base, document_id)
            stop.set()
            codes = reader.result(timeout=30)

        assert codes, "reader made no requests"
        assert all(code < 500 for code in codes), sorted(set(codes))


# --- N+1 regression: documents list issues ONE jobs query ---------------------------


def test_documents_list_batches_latest_job_queries(client):
    """Regression: the documents list used to issue one processing_jobs query
    per row (N+1). It must now batch them into a single query."""
    statements: list[str] = []

    def _record(_conn, _cursor, statement, _params, *args):
        statements.append(statement)

    case = client.post("/api/v1/cases", json={"title": "N+1 Regression"}).json()
    for index in range(6):
        upload = client.post(
            f"/api/v1/cases/{case['id']}/documents",
            files={"file": (f"n1-{index}.pdf", PDF, "application/pdf")},
        )
        assert upload.status_code == 202

    event.listen(engine, "before_cursor_execute", _record)
    try:
        response = client.get(f"/api/v1/cases/{case['id']}/documents")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 6
        jobs_queries = sum("processing_jobs" in s for s in statements)
        assert jobs_queries == 1, f"expected 1 jobs query for the list, saw {jobs_queries}"
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def test_pipeline_on_deleted_document_is_contained(client, seeded_demo):
    """run_pipeline with a vanished document/job fails safely (no crash, no
    partial rows) — covers delete-during-processing recovery."""
    import asyncio

    from app.models import Case

    with SessionLocal() as db:
        case = db.query(Case).first()
        document = Document(
            org_id=case.org_id, case_id=case.id, original_filename="ghost.pdf",
            content_type="application/pdf", size_bytes=1, sha256="0" * 64,
            status="queued", scan_status="skipped", storage_key="2026/01/ghost.pdf",
        )
        db.add(document)
        db.flush()
        job = ProcessingJob(org_id=case.org_id, document_id=document.id, status="queued")
        db.add(job)
        db.commit()
        document_id, job_id = document.id, job.id
        db.delete(document)
        db.commit()

    outcome = asyncio.run(pipeline.run_pipeline(SessionLocal(), document_id, job_id))
    assert outcome.document_status == "failed"

    with SessionLocal() as db:
        assert db.get(Document, document_id) is None
        assert db.query(ProcessingJob).filter(ProcessingJob.document_id == document_id).count() == 0


# --- 0004 migration: duplicate active jobs are superseded, index created ------------


def _seed_migrated_rows(db_file: Path, *, filename: str, doc_status: str) -> str:
    """Insert org/user/case/document + two racing active jobs via raw SQL on a
    pre-0004 schema (matches the 0001-0003 column set exactly)."""
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "INSERT INTO organizations (id, name, slug, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), "Migration Org", f"migration-org-{uuid.uuid4().hex[:8]}", NOW),
        )
        org_id = conn.execute("SELECT id FROM organizations").fetchone()[0]
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, org_id, email, name, role, is_active, created_at)"
            " VALUES (?, ?, ?, ?, 'admin', 1, ?)",
            (user_id, org_id, f"{uuid.uuid4().hex[:8]}@example.com", "Mig", NOW),
        )
        case_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO cases (id, org_id, display_code, title, establishment_name, status,"
            " notes, created_by, created_at, updated_at)"
            " VALUES (?, ?, 'MC-0001', 'Migration Case', '', 'draft', '', ?, ?, ?)",
            (case_id, org_id, user_id, NOW, NOW),
        )
        document_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO documents (id, org_id, case_id, original_filename, storage_key,"
            " content_type, size_bytes, sha256, status, text_chars, extraction_method,"
            " extracted_text, doc_type, doc_type_confidence, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '2026/01/x.pdf', 'application/pdf', 1, ?, ?, 0, 'none',"
            " '', 'unknown', 0, ?, ?)",
            (document_id, org_id, case_id, filename, "0" * 64, doc_status, NOW, NOW),
        )
        for created in (NOW, "2026-09-18 12:01:00"):  # old first, new second
            conn.execute(
                "INSERT INTO processing_jobs (id, org_id, document_id, status, attempts,"
                " created_at) VALUES (?, ?, ?, 'running', 1, ?)",
                (str(uuid.uuid4()), org_id, document_id, created),
            )
        conn.commit()
        return document_id
    finally:
        conn.close()


def _run_alembic(db_file: Path, *args: str) -> None:
    subprocess.run(
        [".venv/bin/alembic", *args],
        env={**os.environ, "DATABASE_URL": f"sqlite:///{db_file}", "APP_ENV": "local", "AUTH_MODE": "demo"},
        cwd=".", check=True, capture_output=True,
    )


def test_migration_supersedes_duplicate_active_jobs(tmp_path: Path):
    """On databases that raced before the fix, the upgrade closes the older
    duplicate active job (keeping the newest) and creates the partial unique
    index; the document keeps its one surviving active job."""
    db_file = tmp_path / "migrate.db"
    _run_alembic(db_file, "upgrade", "0003_identity_link")  # pre-0004 schema
    document_id = _seed_migrated_rows(db_file, filename="dup.pdf", doc_status="processing")
    _run_alembic(db_file, "upgrade", "head")

    conn = sqlite3.connect(db_file)
    try:
        by_status = dict(
            conn.execute(
                "SELECT status, count(*) FROM processing_jobs WHERE document_id = ? GROUP BY status",
                (document_id,),
            ).fetchall()
        )
        assert by_status == {"running": 1, "failed": 1}, by_status
        kept = conn.execute(
            "SELECT created_at FROM processing_jobs WHERE document_id = ? AND status = 'running'",
            (document_id,),
        ).fetchone()[0]
        assert kept == "2026-09-18 12:01:00"  # the NEWEST job survived
        index_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'uq_active_job_per_document'"
        ).fetchone()[0]
        assert "queued" in index_sql and "running" in index_sql  # partial index
        document_status = conn.execute(
            "SELECT status FROM documents WHERE id = ?", (document_id,)
        ).fetchone()[0]
        assert document_status == "processing"  # active job remains → untouched
    finally:
        conn.close()


def test_migration_fails_orphaned_nonterminal_documents(tmp_path: Path):
    """A document stuck non-terminal with NO active job is failed by the
    upgrade so it can be reprocessed instead of hanging forever."""
    db_file = tmp_path / "orphan.db"
    _run_alembic(db_file, "upgrade", "0003_identity_link")
    document_id = _seed_migrated_rows(db_file, filename="stuck.pdf", doc_status="queued")
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("DELETE FROM processing_jobs")  # orphan the document
        conn.commit()
    finally:
        conn.close()
    _run_alembic(db_file, "upgrade", "head")

    conn = sqlite3.connect(db_file)
    try:
        status, error = conn.execute(
            "SELECT status, error FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        assert status == "failed"
        assert "Reprocess" in error
    finally:
        conn.close()


def test_migrated_partial_index_blocks_duplicate_inserts(tmp_path: Path):
    """After upgrade, the database itself refuses a second active job — even
    from raw SQL bypassing the application guard."""
    db_file = tmp_path / "guard.db"
    _run_alembic(db_file, "upgrade", "head")
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "INSERT INTO organizations (id, name, slug, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), "Guard Org", "guard-org", NOW),
        )
        org_id = conn.execute("SELECT id FROM organizations").fetchone()[0]
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, org_id, email, name, role, is_active, created_at)"
            " VALUES (?, ?, ?, ?, 'admin', 1, ?)",
            (user_id, org_id, "guard@example.com", "Guard", NOW),
        )
        case_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO cases (id, org_id, display_code, title, establishment_name, status,"
            " notes, created_by, created_at, updated_at)"
            " VALUES (?, ?, 'GC-0001', 'Guard Case', '', 'draft', '', ?, ?, ?)",
            (case_id, org_id, user_id, NOW, NOW),
        )
        document_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO documents (id, org_id, case_id, original_filename, storage_key,"
            " content_type, size_bytes, sha256, status, text_chars, extraction_method,"
            " extracted_text, doc_type, doc_type_confidence, created_at, updated_at)"
            " VALUES (?, ?, ?, 'g.pdf', '2026/01/g.pdf', 'application/pdf', 1, ?, 'queued',"
            " 0, 'none', '', 'unknown', 0, ?, ?)",
            (document_id, org_id, case_id, "0" * 64, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO processing_jobs (id, org_id, document_id, status, attempts, created_at)"
            " VALUES (?, ?, ?, 'queued', 0, ?)",
            (str(uuid.uuid4()), org_id, document_id, NOW),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO processing_jobs (id, org_id, document_id, status, attempts, created_at)"
                " VALUES (?, ?, ?, 'queued', 0, ?)",
                (str(uuid.uuid4()), org_id, document_id, NOW),
            )
    finally:
        conn.close()
