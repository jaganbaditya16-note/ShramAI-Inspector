from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_case_and_png_upload():
    cases = client.get("/api/v1/cases")
    assert cases.status_code == 200
    case_id = cases.json()["items"][0]["id"]

    image = BytesIO()
    Image.new("RGB", (80, 40), "white").save(image, format="PNG")
    image.seek(0)

    response = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": ("demo.png", image, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is True
    assert body["findings_count"] >= 1
    assert isinstance(body["findings"], list)


def test_upload_rejects_fake_pdf():
    response = client.post(
        "/api/v1/cases/DEMO-001/documents",
        files={"file": ("fake.pdf", BytesIO(b"not a pdf"), "application/pdf")},
    )
    assert response.status_code == 400
