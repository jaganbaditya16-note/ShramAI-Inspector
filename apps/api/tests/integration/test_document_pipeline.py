"""Document upload + processing pipeline integration tests (inline mode)."""

from __future__ import annotations

from app.services.synthetic import build_synthetic_pdf


def _png(width: int = 60, height: int = 40) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(client, case_id: str, data: bytes, filename: str, content_type: str):
    return client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": (filename, data, content_type)},
    )


def test_upload_pdf_processes_and_produces_findings(client, seeded_demo):
    response = _upload(
        client, seeded_demo["case_id"], build_synthetic_pdf(), "payslip-aug.pdf", "application/pdf",
    )
    assert response.status_code == 202
    body = response.json()
    document = body["document"]
    assert document["status"] == "processed"
    assert document["doc_type"] == "payslip"
    assert document["job"]["status"] == "succeeded"
    assert document["job"]["detail"]["rule_findings"] >= 1
    assert document["job"]["detail"]["timings_ms"]["extraction_ms"] >= 0


def test_upload_image_processed(client, seeded_demo):
    response = _upload(client, seeded_demo["case_id"], _png(), "scan.png", "image/png")
    assert response.status_code == 202
    body = response.json()["document"]
    assert body["status"] in {"processed", "failed"}  # depends on OCR availability
    if body["status"] == "processed":
        assert body["doc_type"] == "unknown"


def test_upload_rejects_malicious_fake_pdf(client, seeded_demo):
    response = _upload(
        client, seeded_demo["case_id"], b"not a pdf", "fake.pdf", "application/pdf",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "upload_rejected"
    # Nothing persisted: the failed upload must not leave a document row.
    documents = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/documents").json()
    assert all(item["original_filename"] != "fake.pdf" for item in documents["items"])


def test_upload_requires_file_field(client, seeded_demo):
    response = client.post(f"/api/v1/cases/{seeded_demo['case_id']}/documents")
    assert response.status_code == 422


def test_download_is_authorised_and_streams_original(client, seeded_demo):
    uploaded = _upload(
        client, seeded_demo["case_id"], build_synthetic_pdf(), "payslip.pdf", "application/pdf",
    ).json()["document"]
    download = client.get(f"/api/v1/documents/{uploaded['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/pdf")
    assert download.content.startswith(b"%PDF-")
    assert download.headers["cache-control"] == "no-store"


def test_reprocess_preserves_review_decisions(client, seeded_demo):
    uploaded = _upload(
        client, seeded_demo["case_id"], build_synthetic_pdf(), "payslip.pdf", "application/pdf",
    ).json()["document"]
    findings = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/findings").json()["items"]
    target = next(f for f in findings if f["rule_id"] == "PAY-001")
    reviewed = client.patch(
        f"/api/v1/findings/{target['id']}", json={"status": "confirmed", "note": "Verified missing net pay."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewed_at"] is not None

    reprocessed = client.post(f"/api/v1/documents/{uploaded['id']}/reprocess")
    assert reprocessed.status_code == 202
    assert reprocessed.json()["document"]["status"] == "processed"

    findings_after = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/findings").json()["items"]
    target_after = next(f for f in findings_after if f["rule_id"] == "PAY-001")
    assert target_after["status"] == "confirmed"
    assert target_after["review_note"] == "Verified missing net pay."


def test_background_mode_completes(client, seeded_demo, monkeypatch):
    import time

    from app.core.config import settings

    monkeypatch.setattr(settings, "pipeline_mode", "background")
    response = _upload(
        client, seeded_demo["case_id"], build_synthetic_pdf(), "bg-payslip.pdf", "application/pdf",
    )
    assert response.status_code == 202
    assert response.json()["document"]["status"] == "queued"
    document_id = response.json()["document"]["id"]
    # Poll; each request pumps the app's event loop so the scheduled task runs.
    deadline = time.time() + 15
    final = None
    while time.time() < deadline:
        final = client.get(f"/api/v1/documents/{document_id}").json()
        if final["status"] in {"processed", "failed"}:
            break
        time.sleep(0.1)
    assert final is not None and final["status"] == "processed"
    assert final["job"]["status"] == "succeeded"
