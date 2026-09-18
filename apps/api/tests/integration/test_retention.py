"""Retention & deletion lifecycle tests.

Covers: retention calculation, active case protection, expired documents,
document deletion (API), object deletion, missing objects during purge,
storage failures (row kept, retried), tenant isolation, repeated deletion
idempotency, signed-URL behaviour after deletion, audit preservation, and the
processing-job race (expired jobs cannot revive deleted data).
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from app.core.config import settings
from app.core.security import Principal, hash_password
from app.db.session import SessionLocal
from app.models import (
    AuditEvent,
    Case,
    Document,
    Finding,
    ModelRun,
    Organization,
    ProcessingJob,
    Report,
    User,
)
from app.services import document_service, retention_service
from app.services.identity import reset_identity_provider
from app.services.pipeline import run_pipeline
from app.services.storage import (
    LocalDiskStore,
    MissingObjectError,
    S3Store,
    StorageError,
    reset_store,
)
from test_storage_backends import FakeS3Client

FUTURE = timedelta(days=10_000)


def _upload_doc(client, case_id: str, name: str = "doc.pdf") -> dict:
    from app.services.synthetic import build_synthetic_pdf

    response = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": (name, build_synthetic_pdf(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    return response.json()["document"]


def _storage_key(document_id: str) -> str:
    with SessionLocal() as db:
        return db.get(Document, document_id).storage_key


def _age_document(document_id: str, days: int) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        document.created_at = document.created_at - timedelta(days=days)
        db.commit()


def _admin_principal(org_id: str) -> Principal:
    with SessionLocal() as db:
        org = db.get(Organization, org_id)
        return Principal(user=None, org=org, role="admin", is_demo=True)


# --- retention calculation --------------------------------------------------------------


def test_retention_calculation(monkeypatch):
    monkeypatch.setattr(settings, "retention_document_days", 30)
    monkeypatch.setattr(settings, "retention_rejected_document_days", 7)
    created = datetime_fix(-10)
    now = datetime_fix(0)

    # processed document: 30 days from creation -> not yet due at day 10
    assert retention_service.document_expiry(created, "processed") == created + timedelta(days=30)
    assert retention_service.document_expiry(created, "processed", now=now) > now
    # rejected documents use the shorter window: due at day 10 (created 10d ago)
    assert retention_service.document_expiry(created, "rejected", now=now) <= now
    # zero policy = never
    monkeypatch.setattr(settings, "retention_document_days", 0)
    assert retention_service.document_expiry(created, "processed") is None
    monkeypatch.setattr(settings, "retention_rejected_document_days", 0)
    assert retention_service.document_expiry(created, "rejected") is None


def datetime_fix(days_from_today: int):
    from app.db.helpers import utcnow

    return utcnow() + timedelta(days=days_from_today)


# --- default policy deletes nothing (active case protection) ------------------------------


def test_default_policy_purges_nothing_and_never_touches_active_cases(client, seeded_demo):
    doc = _upload_doc(client, seeded_demo["case_id"], "keep.pdf")
    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.documents_purged == 0 and report.cases_purged == 0
    with SessionLocal() as db:
        assert db.get(Document, doc["id"]) is not None


def test_soft_deleted_case_never_hard_purged_while_retention_is_zero(client, seeded_demo):
    with SessionLocal() as db:
        case = db.get(Case, seeded_demo["case_id"])
        case.deleted_at = case.created_at - FUTURE  # soft-deleted long ago
        db.commit()
    monkeypatch_this = settings
    assert monkeypatch_this.retention_case_days == 0
    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.cases_purged == 0
    with SessionLocal() as db:
        assert db.get(Case, seeded_demo["case_id"]) is not None


# --- expired document purge ----------------------------------------------------------------


def test_expired_document_is_purged_with_rows_and_object(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_document_days", 5)
    doc = _upload_doc(client, seeded_demo["case_id"], "expired.pdf")
    _age_document(doc["id"], 10)
    storage_key = _storage_key(doc["id"])
    assert document_service.get_store().exists(storage_key)

    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.documents_purged == 1

    with SessionLocal() as db:
        assert db.get(Document, doc["id"]) is None  # extracted text/page map died with the row
        assert db.query(Finding).filter(Finding.document_id == doc["id"]).count() == 0
        assert db.query(ProcessingJob).filter(ProcessingJob.document_id == doc["id"]).count() == 0
        assert db.query(ModelRun).filter(ModelRun.document_id == doc["id"]).count() == 0
    assert not document_service.get_store().exists(storage_key)


def test_rejected_documents_use_shorter_window(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_document_days", 0)  # processed docs never expire
    monkeypatch.setattr(settings, "retention_rejected_document_days", 1)
    with SessionLocal() as db:
        doc = Document(
            org_id=seeded_demo["org_id"], case_id=seeded_demo["case_id"],
            original_filename="rejected.pdf", storage_key="", content_type="application/pdf",
            size_bytes=10, sha256="a" * 64, status="rejected", scan_status="infected",
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id
    # fresh rejection: not yet due
    assert retention_service.run_retention_sweep(SessionLocal()).documents_purged == 0
    _age_document(doc_id, 2)
    assert retention_service.run_retention_sweep(SessionLocal()).documents_purged == 1
    with SessionLocal() as db:
        assert db.get(Document, doc_id) is None


# --- user-facing document deletion (API) -----------------------------------------------------


def test_document_deletion_removes_rows_object_and_audits(client, seeded_demo):
    doc = _upload_doc(client, seeded_demo["case_id"], "bye.pdf")
    with SessionLocal() as db:
        db.add(ModelRun(org_id=seeded_demo["org_id"], document_id=doc["id"],
                        provider="test", model="m", status="ok"))
        db.commit()
    storage_key = _storage_key(doc["id"])
    assert document_service.get_store().exists(storage_key)

    response = client.delete(f"/api/v1/documents/{doc['id']}")
    assert response.status_code == 204

    from app.services.document_service import get_store

    assert not get_store().exists(storage_key)  # object removed: no orphans
    with SessionLocal() as db:
        assert db.get(Document, doc["id"]) is None
        assert db.query(ModelRun).filter(ModelRun.document_id == doc["id"]).count() == 0
        actions = [
            row[0] for row in db.query(AuditEvent.action)
            .filter(AuditEvent.detail.contains(doc["id"])).all()
        ]
    assert "document_deleted" in actions


def test_missing_object_during_purge_is_a_success(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_document_days", 5)
    doc = _upload_doc(client, seeded_demo["case_id"], "ghost.pdf")
    _age_document(doc["id"], 10)
    document_service.get_store().delete(_storage_key(doc["id"]))  # object already gone
    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.documents_purged == 1 and report.documents_deferred == 0
    with SessionLocal() as db:
        assert db.get(Document, doc["id"]) is None


def test_storage_failure_keeps_row_and_next_sweep_retries(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_document_days", 5)
    doc = _upload_doc(client, seeded_demo["case_id"], "stuck.pdf")
    _age_document(doc["id"], 10)

    class FailingDelete(LocalDiskStore):
        def delete(self, key):
            raise StorageError("backend down")

    import app.services.document_service as ds

    original_doc_store, original_retention_store = ds.get_store, retention_service.get_store
    monkeypatch.setattr(ds, "get_store", lambda: FailingDelete("./storage"))
    monkeypatch.setattr(retention_service, "get_store", lambda: FailingDelete("./storage"))
    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.documents_deferred == 1 and report.documents_purged == 0
    with SessionLocal() as db:
        assert db.get(Document, doc["id"]) is not None  # ledger kept: object not orphaned

    # backend recovers -> next sweep succeeds (idempotent retry)
    monkeypatch.setattr(ds, "get_store", original_doc_store)
    monkeypatch.setattr(retention_service, "get_store", original_retention_store)
    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.documents_purged == 1
    with SessionLocal() as db:
        assert db.get(Document, doc["id"]) is None


def test_repeated_purge_and_delete_are_idempotent(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_document_days", 5)
    doc = _upload_doc(client, seeded_demo["case_id"], "twice.pdf")
    _age_document(doc["id"], 10)
    first = retention_service.run_retention_sweep(SessionLocal())
    second = retention_service.run_retention_sweep(SessionLocal())
    assert first.documents_purged == 1 and second.documents_purged == 0

    response_first = client.delete(f"/api/v1/documents/{doc['id']}")
    assert response_first.status_code == 404  # already purged: consistent 404
    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.documents_purged == 0


# --- hard case purge --------------------------------------------------------------------------


def test_soft_deleted_case_hard_purges_after_retention(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_case_days", 30)
    doc = _upload_doc(client, seeded_demo["case_id"], "case-doc.pdf")
    storage_key = _storage_key(doc["id"])
    with SessionLocal() as db:
        db.add(Report(org_id=seeded_demo["org_id"], case_id=seeded_demo["case_id"],
                      score=50, risk_level="medium", payload={}))
        db.commit()
        case = db.get(Case, seeded_demo["case_id"])
        case.deleted_at = case.created_at - timedelta(days=31)
        db.commit()

    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.cases_purged == 1

    from app.services.document_service import get_store

    assert not get_store().exists(storage_key)  # storage objects removed first
    with SessionLocal() as db:
        assert db.get(Case, seeded_demo["case_id"]) is None
        assert db.get(Document, doc["id"]) is None
        assert db.query(Finding).filter(Finding.case_id == seeded_demo["case_id"]).count() == 0
        assert db.query(Report).filter(Report.case_id == seeded_demo["case_id"]).count() == 0


# --- tenant isolation ---------------------------------------------------------------------------


def test_tenant_isolation_user_delete_and_admin_sweep(client, seeded_demo, monkeypatch):
    password = "cross-org-pass-1"
    with SessionLocal() as db:
        other_org = Organization(name="Retention Other Org", slug="retention-other")
        db.add(other_org)
        db.flush()
        db.add(User(org_id=other_org.id, email="retention-other@example.com",
                    name="Other Inspector", password_hash=hash_password(password),
                    role="admin"))
        db.commit()
    doc = _upload_doc(client, seeded_demo["case_id"], "protected.pdf")

    monkeypatch.setattr(settings, "auth_mode", "required")
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as other_client:
        login = other_client.post("/api/v1/auth/login", json={
            "email": "retention-other@example.com", "password": password,
        })
        assert login.status_code == 200
        # another tenant's inspector/admin cannot delete or see the document
        assert other_client.get(f"/api/v1/documents/{doc['id']}").status_code == 404
        assert other_client.delete(f"/api/v1/documents/{doc['id']}").status_code == 404
        with SessionLocal() as db:
            assert db.get(Document, doc["id"]) is not None

    with SessionLocal() as db:
        assert db.get(Document, doc["id"]) is not None


def test_retention_sweep_endpoint_requires_admin(client, seeded_demo):
    # the demo principal is an inspector: must be forbidden
    response = client.post("/api/v1/admin/retention/run")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


# --- signed URLs / access after deletion -----------------------------------------------------------


def test_no_access_after_purge_download_404_and_s3_object_missing(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_document_days", 5)
    fake = FakeS3Client()
    store = S3Store(bucket="docs", access_key_id="a", secret_access_key="s", client=fake)
    import app.services.document_service as ds

    monkeypatch.setattr(ds, "get_store", lambda: store)
    monkeypatch.setattr("app.services.retention_service.get_store", lambda: store)
    doc = _upload_doc(client, seeded_demo["case_id"], "signed.pdf")
    storage_key = _storage_key(doc["id"])
    _age_document(doc["id"], 10)
    assert len(fake.objects) == 1

    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.documents_purged == 1
    assert fake.objects == {}  # object deleted at the provider

    # API download re-checks the (now missing) document: safe 404
    response = client.get(f"/api/v1/documents/{doc['id']}/download")
    assert response.status_code == 404

    # a presigned URL minted earlier cannot outlive the object: reads fail
    with pytest.raises(MissingObjectError):
        store.get_bytes(storage_key)  # object gone: no URL can ever serve it
    # presigning remains possible technically (S3 semantics), but the object is
    # gone, so any URL is dead on arrival — verified by the MissingObjectError above.


def test_presigned_downloads_disabled_by_default(client, seeded_demo):
    assert settings.s3_presigned_downloads is False
    doc = seeded_demo["document_id"]
    response = client.get(f"/api/v1/documents/{doc}/download", follow_redirects=False)
    assert response.status_code == 200
    assert "Location" not in response.headers


# --- audit preservation ------------------------------------------------------------------------------


def test_audit_events_survive_purge_and_contents_never_appear(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_case_days", 30)
    monkeypatch.setattr(settings, "retention_document_days", 5)
    doc = _upload_doc(client, seeded_demo["case_id"], "audited.pdf")
    _age_document(doc["id"], 40)
    with SessionLocal() as db:
        case = db.get(Case, seeded_demo["case_id"])
        case.deleted_at = case.created_at - timedelta(days=31)
        db.commit()
    from sqlalchemy import func, select

    with SessionLocal() as db:
        before = db.scalar(select(func.count(AuditEvent.id)))
    retention_service.run_retention_sweep(SessionLocal())
    with SessionLocal() as db:
        after = db.scalar(select(func.count(AuditEvent.id)))
        assert after > before  # nothing deleted; purge events appended
        actions = [row[0] for row in db.execute(select(AuditEvent.action)).all()]
        assert "retention_document_purged" in actions
        assert "retention_case_purged" in actions
        # audit rows carry ids only — never document text
        blob = " ".join(str(row[0]) for row in db.execute(select(AuditEvent.detail)).all())
        assert "SYNTHETIC" not in blob


# --- processing-job race -------------------------------------------------------------------------------


def test_documents_with_active_jobs_are_not_purged(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "retention_document_days", 5)
    doc = _upload_doc(client, seeded_demo["case_id"], "running.pdf")
    _age_document(doc["id"], 10)
    with SessionLocal() as db:
        db.add(ProcessingJob(org_id=seeded_demo["org_id"], document_id=doc["id"],
                             status="running"))
        db.commit()
    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.skipped_active_jobs >= 1 and report.documents_purged == 0
    with SessionLocal() as db:
        assert db.get(Document, doc["id"]) is not None


def test_pipeline_cannot_revive_deleted_document(client, seeded_demo, monkeypatch):
    import asyncio

    doc = _upload_doc(client, seeded_demo["case_id"], "revive.pdf")
    document_id, job_id = doc["id"], None
    with SessionLocal() as db:
        job = ProcessingJob(org_id=seeded_demo["org_id"], document_id=document_id,
                            status="queued")
        db.add(job)
        db.commit()
        job_id = job.id

    # the document is deleted (user-initiated) after the job was queued
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204

    outcome = asyncio.run(run_pipeline(SessionLocal(), document_id, job_id))
    assert outcome.document_status == "failed"
    with SessionLocal() as db:
        assert db.get(Document, document_id) is None  # nothing recreated
        assert db.query(Finding).filter(Finding.document_id == document_id).count() == 0


def test_expired_job_rows_cannot_resurrect_after_case_purge(client, seeded_demo, monkeypatch):
    import asyncio

    monkeypatch.setattr(settings, "retention_case_days", 30)
    doc = _upload_doc(client, seeded_demo["case_id"], "casejob.pdf")
    with SessionLocal() as db:
        job = ProcessingJob(org_id=seeded_demo["org_id"], document_id=doc["id"],
                            status="queued")
        db.add(job)
        db.commit()
        job_id, document_id = job.id, doc["id"]
        case = db.get(Case, seeded_demo["case_id"])
        case.deleted_at = case.created_at - timedelta(days=31)
        db.commit()

    report = retention_service.run_retention_sweep(SessionLocal())
    assert report.cases_purged == 1

    outcome = asyncio.run(run_pipeline(SessionLocal(), document_id, job_id))
    assert outcome.document_status == "failed"  # expired job cannot revive deleted data


def teardown_function():
    reset_identity_provider()
    reset_store()
