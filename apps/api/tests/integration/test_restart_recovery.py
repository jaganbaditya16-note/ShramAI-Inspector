"""Restart-recovery regression: jobs interrupted by a restart must fail safely
so clients can reprocess, and documents must never stay stuck in processing."""

from __future__ import annotations

from app.db.session import SessionLocal
from app.models import Document, ProcessingJob
from app.services.pipeline import recover_interrupted_jobs
from app.services.synthetic import build_synthetic_pdf


def test_stale_jobs_recovered_on_startup(client, seeded_demo):
    """Simulate a crash: leave a document 'processing' with a 'running' job."""
    with SessionLocal() as db:
        document = db.get(Document, seeded_demo["document_id"])
        document.status = "processing"
        jobs = db.query(ProcessingJob).filter(ProcessingJob.document_id == document.id).all()
        assert jobs
        jobs[0].status = "running"
        db.commit()
        document_id = document.id

    # New process starts and runs recovery (this is what lifespan does).
    with SessionLocal() as db:
        recovered = recover_interrupted_jobs(db)
        assert recovered == 1
        document = db.get(Document, document_id)
        assert document.status == "failed"
        assert "restart" in (document.error or "").lower()
        jobs = db.query(ProcessingJob).filter(ProcessingJob.document_id == document_id).all()
        assert all(j.status == "failed" for j in jobs)

    # API reflects the failed state and allows reprocessing.
    listing = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/documents").json()
    target = next(item for item in listing["items"] if item["id"] == document_id)
    assert target["status"] == "failed"

    reprocessed = client.post(f"/api/v1/documents/{document_id}/reprocess")
    assert reprocessed.status_code == 202
    assert reprocessed.json()["document"]["status"] in {"queued", "processed"}


def test_recovery_is_idempotent(client, seeded_demo):
    with SessionLocal() as db:
        assert recover_interrupted_jobs(db) >= 0
        # A second run with nothing stale recovers nothing new.
        assert recover_interrupted_jobs(db) == 0


def test_uploaded_pdf_roundtrip(client, seeded_demo):
    """Upload the synthetic PDF through the API in background mode and verify
    the full pipeline marks it processed (restart-safe path)."""
    import time

    from app.core.config import settings

    previous = settings.pipeline_mode
    settings.pipeline_mode = "background"
    try:
        response = client.post(
            f"/api/v1/cases/{seeded_demo['case_id']}/documents",
            files={"file": ("roundtrip.pdf", build_synthetic_pdf(), "application/pdf")},
        )
        assert response.status_code == 202
        document_id = response.json()["document"]["id"]
        deadline = time.time() + 15
        status = None
        while time.time() < deadline:
            document = client.get(f"/api/v1/documents/{document_id}").json()
            status = document["status"]
            if status in {"processed", "failed"}:
                break
            time.sleep(0.1)
        assert status == "processed"
    finally:
        settings.pipeline_mode = previous
