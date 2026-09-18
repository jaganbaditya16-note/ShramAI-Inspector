"""Integration tests: production document storage.

Exercises the upload→store→download lifecycle through the real API for both
backends (local disk is the default; an S3-backed run injects a fake botocore
client), plus failure paths: missing objects, backend failures at
upload/download/delete, orphan cleanup, tenant isolation, unauthorised access
and the optional short-lived presigned-URL mode.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Document
from app.services.storage import LocalDiskStore, S3Store, StorageError, reset_store
from app.services.synthetic import build_synthetic_pdf
from test_storage_backends import FakeS3Client


def _pdf() -> bytes:
    return build_synthetic_pdf()


def _upload(client, case_id: str, data: bytes, name: str = "doc.pdf"):
    return client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": (name, data, "application/pdf")},
    )


# --- upload → download roundtrip preserves integrity -------------------------------


def test_upload_and_download_roundtrip_preserves_sha256(client, seeded_demo):
    data = _pdf()
    response = _upload(client, seeded_demo["case_id"], data, "roundtrip.pdf")
    assert response.status_code == 202
    document = response.json()["document"]
    assert document["status"] in {"queued", "processing", "processed"}

    downloaded = client.get(f"/api/v1/documents/{document['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == data  # byte-exact integrity
    assert downloaded.headers["Cache-Control"] == "no-store"
    assert "attachment" in downloaded.headers.get("content-disposition", "")
    assert hashlib.sha256(downloaded.content).hexdigest() == hashlib.sha256(data).hexdigest()

    stored = client.get(f"/api/v1/documents/{document['id']}").json()
    assert stored["sha256"] == hashlib.sha256(data).hexdigest()


def test_upload_via_s3_backend_streams_back_through_api(client, seeded_demo, monkeypatch):
    fake = FakeS3Client()
    monkeypatch.setattr(
        "app.services.document_service.get_store",
        lambda: S3Store(
            bucket="docs", access_key_id="a", secret_access_key="s", client=fake
        ),
    )
    data = _pdf()
    response = _upload(client, seeded_demo["case_id"], data, "s3-backend.pdf")
    assert response.status_code == 202
    assert len(fake.objects) == 1  # exactly one private object written

    downloaded = client.get(f"/api/v1/documents/{response.json()['document']['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == data  # streamed via the API, no URLs involved


# --- missing object ------------------------------------------------------------------


def test_missing_object_download_is_safe_404(client, seeded_demo):
    data = _pdf()
    document = _upload(client, seeded_demo["case_id"], data, "vanish.pdf").json()["document"]

    # storage keys are never exposed via the API: read it from the DB, then
    # delete the object behind the API (simulate storage-side loss / expiry)
    from app.services import document_service

    with SessionLocal() as db:
        storage_key = db.get(Document, document["id"]).storage_key
    document_service.get_store().delete(storage_key)

    response = client.get(f"/api/v1/documents/{document['id']}/download")
    assert response.status_code == 404
    assert "missing" in response.json()["error"]["message"].lower()


# --- storage failures -----------------------------------------------------------------


def test_upload_fails_closed_when_storage_write_fails(client, seeded_demo, monkeypatch):
    class FailingStore(LocalDiskStore):
        def save(self, data, suffix):
            raise StorageError("The storage backend rejected the write.")

    monkeypatch.setattr(
        "app.services.document_service.get_store", lambda: FailingStore("./storage")
    )
    response = _upload(client, seeded_demo["case_id"], _pdf(), "failing.pdf")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"

    listing = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/documents").json()
    assert all(item["original_filename"] != "failing.pdf" for item in listing["items"])
    with SessionLocal() as db:
        assert db.query(Document).filter(Document.original_filename == "failing.pdf").count() == 0


def test_no_orphaned_object_when_registration_fails(client, seeded_demo, monkeypatch):
    """If the DB write fails after the object was stored, the object is removed."""
    fake = FakeS3Client()
    store = S3Store(bucket="docs", access_key_id="a", secret_access_key="s", client=fake)
    monkeypatch.setattr("app.services.document_service.get_store", lambda: store)

    import app.services.document_service as ds

    original = ds.audit_service.record

    def exploding_record(*args, **kwargs):
        if kwargs.get("action") == "document_uploaded":
            raise RuntimeError("simulated commit-time failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(ds.audit_service, "record", exploding_record)
    with pytest.raises(RuntimeError, match="simulated commit-time failure"):
        _upload(client, seeded_demo["case_id"], _pdf(), "orphan.pdf")
    assert fake.objects == {}  # best-effort cleanup removed the orphaned object
    with SessionLocal() as db:
        assert db.query(Document).filter(Document.original_filename == "orphan.pdf").count() == 0


def test_download_fails_safe_when_backend_unavailable(client, seeded_demo, monkeypatch):
    data = _pdf()
    document = _upload(client, seeded_demo["case_id"], data, "later.pdf").json()["document"]

    class BrokenGetStore(LocalDiskStore):
        def get_bytes(self, key):
            raise StorageError("backend unreachable")

    # force the ephemeral (S3-style) code path so get_bytes is exercised
    broken = BrokenGetStore("./storage")
    broken.ephemeral_paths = True
    monkeypatch.setattr("app.services.document_service.get_store", lambda: broken)

    response = client.get(f"/api/v1/documents/{document['id']}/download")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"


def test_delete_is_safe_when_storage_fails_or_object_missing(
    client, seeded_demo, monkeypatch
):
    from app.core.errors import StorageUnavailable
    from app.core.security import Principal
    from app.models import Organization
    from app.services import document_service

    data = _pdf()
    document = _upload(client, seeded_demo["case_id"], data, "del.pdf").json()["document"]

    class FailingDelete(LocalDiskStore):
        def delete(self, key):
            raise StorageError("backend down")

    class MissingDelete(LocalDiskStore):
        def delete(self, key):
            return None  # idempotent success: missing object is already deleted

    monkeypatch.setattr(
        "app.services.document_service.get_store", lambda: FailingDelete("./storage")
    )
    with SessionLocal() as db:
        row = db.get(Document, document["id"])
        org = db.get(Organization, seeded_demo["org_id"])
        principal = Principal(user=None, org=org, role="inspector", is_demo=True)
        with pytest.raises(StorageUnavailable):
            document_service.delete_document(db, principal, row)
        assert db.get(Document, document["id"]) is not None  # row kept: no dangling record

    monkeypatch.setattr(
        "app.services.document_service.get_store", lambda: MissingDelete("./storage")
    )
    with SessionLocal() as db:
        row = db.get(Document, document["id"])
        org = db.get(Organization, seeded_demo["org_id"])
        principal = Principal(user=None, org=org, role="inspector", is_demo=True)
        document_service.delete_document(db, principal, row)  # missing object: proceeds
        db.commit()
        assert db.get(Document, document["id"]) is None


# --- tenant isolation / unauthorised access -------------------------------------------


def _make_org_with_user(slug: str, email: str, password: str, role: str = "admin") -> None:
    from app.core.security import hash_password
    from app.models import Organization, User

    with SessionLocal() as db:
        org = Organization(name=f"Org {slug}", slug=slug)
        db.add(org)
        db.flush()
        db.add(User(
            org_id=org.id, email=email, name=f"Inspector {slug}",
            password_hash=hash_password(password), role=role,
        ))
        db.commit()


def _login(client, email: str, password: str):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return client


def test_cross_tenant_document_read_and_download_are_404(client, seeded_demo, monkeypatch):
    password_a, password_b = "isolation-pass-a-1", "isolation-pass-b-1"
    _make_org_with_user("org-a", "a@example.com", password_a)
    _make_org_with_user("org-b", "b@example.com", password_b)
    monkeypatch.setattr(settings, "auth_mode", "required")

    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client_a:
        _login(client_a, "a@example.com", password_a)
        uploaded = _upload(client_a, _first_case(client_a), _pdf(), "secret-a.pdf")
        assert uploaded.status_code == 202
        document_id = uploaded.json()["document"]["id"]
        # owner can download
        assert client_a.get(f"/api/v1/documents/{document_id}/download").status_code == 200

    with TestClient(app) as client_b:
        _login(client_b, "b@example.com", password_b)
        assert client_b.get(f"/api/v1/documents/{document_id}").status_code == 404
        assert client_b.get(f"/api/v1/documents/{document_id}/download").status_code == 404


def _first_case(client) -> str:
    org_case = client.post(
        "/api/v1/cases", json={"title": "Isolation Case"},
    )
    assert org_case.status_code == 201
    return org_case.json()["id"]


def test_anonymous_download_is_unauthorized(client, seeded_demo, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "required")
    with SessionLocal() as db:
        doc = db.query(Document).first()
        document_id = doc.id
    response = client.get(f"/api/v1/documents/{document_id}/download")
    assert response.status_code == 401


def test_traversal_style_document_ids_cannot_reach_storage(client, seeded_demo):
    for payload in ("..%2F..%2Fetc%2Fpasswd", "%2e%2e%2f%2e%2e%2fsecret.pdf", "x" * 400):
        response = client.get(f"/api/v1/documents/{payload}/download")
        assert response.status_code in {400, 404}


# --- optional short-lived presigned downloads -------------------------------------------


def test_presigned_downloads_disabled_by_default_streams_bytes(client, seeded_demo):
    assert settings.s3_presigned_downloads is False
    document = seeded_demo["document_id"]
    response = client.get(f"/api/v1/documents/{document}/download")
    assert response.status_code == 200
    assert "Location" not in response.headers  # no redirect, no URL exposure


def test_presigned_download_mode_redirects_to_short_lived_url(client, seeded_demo, monkeypatch):
    fake = FakeS3Client()
    store = S3Store(bucket="docs", access_key_id="a", secret_access_key="s", client=fake)
    monkeypatch.setattr("app.services.document_service.get_store", lambda: store)
    monkeypatch.setattr(settings, "s3_presigned_downloads", True)
    monkeypatch.setattr(settings, "s3_presign_ttl_seconds", 300)

    with SessionLocal() as db:
        storage_key = db.get(Document, seeded_demo["document_id"]).storage_key
    fake.objects[storage_key] = _pdf()
    response = client.get(
        f"/api/v1/documents/{seeded_demo['document_id']}/download",
        follow_redirects=False,
    )

    assert response.status_code == 307
    location = response.headers["Location"]
    assert "X-Amz-Signature" in location
    assert "X-Amz-Expires=300" in location  # short-lived, never a public URL
    assert response.headers["Cache-Control"] == "no-store"


def test_health_reports_storage_posture_without_secrets(client):
    health = client.get("/api/v1/health").json()
    assert health["storage"]["backend"] == "local"
    assert health["storage"]["bucket"] is None
    assert health["storage"]["presigned_downloads"] is False
    body = repr(health)
    assert "secret" not in body.lower().replace("presigned_downloads", "")


# --- startup validation -----------------------------------------------------------------


def test_s3_backend_without_credentials_refuses_to_boot(monkeypatch):
    from app.main import validate_security_config

    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "")
    monkeypatch.setattr(settings, "s3_access_key_id", "ak")
    monkeypatch.setattr(settings, "s3_secret_access_key", "sk")
    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        validate_security_config()


def test_production_with_local_storage_refuses_to_boot(monkeypatch):
    from app.main import validate_security_config

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "malware_scan_mode", "enforcing")
    monkeypatch.setattr(settings, "clamd_host", "clamd")
    with pytest.raises(RuntimeError, match="STORAGE_BACKEND=local"):
        validate_security_config()


def teardown_function():
    reset_store()
