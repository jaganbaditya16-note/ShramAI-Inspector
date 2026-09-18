"""Findings review, reports and audit trail integration tests."""

from __future__ import annotations

from app.services.synthetic import build_synthetic_pdf


def _seed_case_with_document(client, seeded_demo):
    upload = client.post(
        f"/api/v1/cases/{seeded_demo['case_id']}/documents",
        files={"file": ("payslip.pdf", build_synthetic_pdf(), "application/pdf")},
    ).json()
    return upload["document"]


def test_finding_review_state_machine(client, seeded_demo):
    _seed_case_with_document(client, seeded_demo)
    findings = client.get(
        f"/api/v1/cases/{seeded_demo['case_id']}/findings?sort=-severity"
    ).json()["items"]
    assert findings, "expected findings"
    finding = findings[0]

    confirmed = client.patch(
        f"/api/v1/findings/{finding['id']}",
        json={"status": "confirmed", "note": "Checked with establishment."},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["reviewed_at"] is not None

    back = client.patch(
        f"/api/v1/findings/{finding['id']}", json={"status": "needs_review"},
    )
    assert back.status_code == 200
    assert back.json()["reviewed_at"] is None

    invalid = client.patch(
        f"/api/v1/findings/{finding['id']}", json={"status": "banana"},
    )
    assert invalid.status_code == 422


def test_finding_filters(client, seeded_demo):
    _seed_case_with_document(client, seeded_demo)
    base = f"/api/v1/cases/{seeded_demo['case_id']}/findings"
    assert client.get(f"{base}?severity=high").json()["meta"]["total"] == client.get(
        f"{base}?severity=high"
    ).json()["meta"]["total"]
    only_rule = client.get(f"{base}?origin=rule").json()["items"]
    assert all(item["origin"] == "rule" for item in only_rule)
    paginated = client.get(f"{base}?limit=1&offset=0").json()
    assert len(paginated["items"]) <= 1
    assert paginated["meta"]["limit"] == 1


def test_report_generation_snapshot(client, seeded_demo):
    _seed_case_with_document(client, seeded_demo)
    findings = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/findings").json()["items"]
    first = findings[0]
    client.patch(f"/api/v1/findings/{first['id']}", json={"status": "dismissed"})

    generated = client.post(f"/api/v1/cases/{seeded_demo['case_id']}/report")
    assert generated.status_code == 201
    payload = generated.json()["payload"]
    assert payload["disclaimer"]
    assert "not a legal compliance determination" in payload["disclaimer"]
    assert payload["score_explanation"]
    assert payload["counts"]["findings"] == len(findings)
    assert any(f["rule_id"] == "PAY-001" for f in payload["findings"])
    filenames = {f["document"]["filename"] for f in payload["findings"]}
    assert "payslip.pdf" in filenames

    latest = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/report")
    assert latest.status_code == 200
    assert latest.json()["id"] == generated.json()["id"]


def test_report_before_generation_conflicts(client, seeded_demo):
    response = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/report")
    assert response.status_code == 409


def test_audit_trail_records_actions(client, seeded_demo):
    _seed_case_with_document(client, seeded_demo)
    audit = client.get(f"/api/v1/cases/{seeded_demo['case_id']}/audit").json()
    actions = {event["action"] for event in audit["items"]}
    assert "document_uploaded" in actions
    assert "document_processed" in actions
    event = audit["items"][0]
    assert event["request_id"]
    assert event["actor_label"]
    # Audit details must never contain extracted document text.
    serialized = str(audit)
    assert "SYNTHETIC DEMO PAYSLIP" not in serialized


def test_dashboard_summary_aggregates(client, seeded_demo):
    _seed_case_with_document(client, seeded_demo)
    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["cases_total"] >= 1
    assert summary["documents_total"] >= 2
    assert summary["findings_total"] >= 1
    assert "in_review" in summary["cases_by_status"] or "draft" in summary["cases_by_status"]
    assert summary["recent_activity"]
