from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_system_reports_accelerator():
    response = client.get("/api/system")
    assert response.status_code == 200
    assert response.json()["recommended_device"] in {"cpu", "mps", "cuda"}


def test_job_requires_existing_video():
    response = client.post("/api/jobs", json={
        "video_id": "a" * 32,
        "lines": [{
            "id": "linea-1", "name": "Norte", "x1": .1, "y1": .2,
            "x2": .9, "y2": .2, "positive_direction": "entrada",
        }],
        "classes": ["auto"],
    })
    assert response.status_code == 404


def test_validation_error_identifies_invalid_field():
    response = client.post("/api/jobs", json={"video_id": "incorrecto", "lines": [], "classes": []})
    assert response.status_code == 422
    assert "video_id" in response.json()["detail"]
