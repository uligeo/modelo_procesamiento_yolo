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
            "id": "linea-1", "name": "Norte", "road_name": "Calle 47B E", "x1": .1, "y1": .2,
            "x2": .9, "y2": .2, "positive_direction": "entrada",
        }],
        "classes": ["auto"],
    })
    assert response.status_code == 404


def test_validation_error_identifies_invalid_field():
    response = client.post("/api/jobs", json={"video_id": "incorrecto", "lines": [], "classes": []})
    assert response.status_code == 422
    assert "video_id" in response.json()["detail"]


def test_temporary_video_can_be_deleted(monkeypatch, tmp_path):
    from app import main

    video_id = "b" * 32
    temporary_video = tmp_path / f"{video_id}.mp4"
    temporary_video.write_bytes(b"temporary")
    monkeypatch.setattr(main, "UPLOADS", tmp_path)

    response = client.delete(f"/api/videos/{video_id}")

    assert response.status_code == 204
    assert not temporary_video.exists()


def test_startup_cleanup_preserves_placeholder(tmp_path):
    from app.main import clear_orphan_uploads

    placeholder = tmp_path / ".gitkeep"
    orphan = tmp_path / "orphan.mp4"
    placeholder.touch()
    orphan.write_bytes(b"temporary")

    clear_orphan_uploads(tmp_path)

    assert placeholder.exists()
    assert not orphan.exists()
