"""Health endpoint and demo workspace seeding integration tests."""

from __future__ import annotations


def test_health_reports_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["ai"]["configured"] is False  # OLLAMA_MODEL unset in tests


def test_openapi_available(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert "ShramAI Inspector" in response.json()["info"]["title"]


def test_demo_mode_seeds_synthetic_workspace(client):
    listing = client.get("/api/v1/cases").json()
    assert listing["meta"]["total"] >= 1
    case = listing["items"][0]
    assert case["document_count"] >= 1

    documents = client.get(f"/api/v1/cases/{case['id']}/documents").json()
    document = documents["items"][0]
    assert document["status"] == "processed"
    assert document["doc_type"] == "payslip"
    assert document["job"]["status"] == "succeeded"

    findings = client.get(f"/api/v1/cases/{case['id']}/findings").json()
    rule_ids = {f["rule_id"] for f in findings["items"]}
    assert "PAY-001" in rule_ids  # synthetic payslip omits net pay


def test_root_and_docs_smoke(client):
    assert client.get("/").status_code == 200
    docs_page = client.get("/api/docs")
    assert docs_page.status_code == 200
