"""Case CRUD integration tests."""

from __future__ import annotations


def test_create_and_list_case(client):
    created = client.post("/api/v1/cases", json={
        "title": "Site B Wage Register Review",
        "establishment_name": "Synthetic Constructions Ltd.",
        "establishment_reference": "SYN-777",
    })
    assert created.status_code == 201
    body = created.json()
    assert body["display_code"].startswith("SH-")
    assert body["status"] == "draft"
    assert body["document_count"] == 0

    listing = client.get("/api/v1/cases").json()
    assert listing["meta"]["total"] >= 2  # demo case + new case
    assert any(item["id"] == body["id"] for item in listing["items"])


def test_create_case_validation(client):
    response = client.post("/api/v1/cases", json={"title": "ab"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_update_and_status_transitions(client):
    created = client.post("/api/v1/cases", json={"title": "Transition Case"}).json()
    updated = client.patch(f"/api/v1/cases/{created['id']}", json={
        "title": "Renamed Case", "status": "in_review",
    })
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_review"

    closed = client.patch(f"/api/v1/cases/{created['id']}", json={"status": "closed"})
    assert closed.status_code == 200
    illegal = client.patch(f"/api/v1/cases/{created['id']}", json={"status": "in_review"})
    assert illegal.status_code == 422
    reopen = client.patch(f"/api/v1/cases/{created['id']}", json={"status": "draft"})
    assert reopen.status_code == 200


def test_soft_delete_hides_case(client):
    created = client.post("/api/v1/cases", json={"title": "Doomed Case"}).json()
    deleted = client.delete(f"/api/v1/cases/{created['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/cases/{created['id']}").status_code == 404
    listing = client.get("/api/v1/cases").json()
    assert all(item["id"] != created["id"] for item in listing["items"])


def test_unknown_case_is_404_envelope(client):
    response = client.get("/api/v1/cases/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"].startswith("req_")
