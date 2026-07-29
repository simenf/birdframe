from pathlib import Path

from fastapi.testclient import TestClient

from birdframe.main import create_app


def test_detection_generates_identical_current_display_artifact(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        settings = client.get("/api/v1/settings").json()
        settings.update({"output_width": 640, "output_height": 360, "display_api_enabled": True})
        assert client.put("/api/v1/settings", json=settings).status_code == 200
        created = client.post("/api/v1/detections", json={
            "common_name": "Eurasian Blackbird", "scientific_name": "Turdus merula", "confidence": 0.91,
        })
        assert created.status_code == 201
        metadata = client.get("/api/v1/display/current.json").json()
        assert metadata["image_url"].endswith(f"?revision={metadata['revision']}")
        image = client.get("/api/v1/display/current.jpg")
        assert image.status_code == 200
        assert image.headers["etag"].strip('"') == metadata["sha256"]
        assert len(image.content) > 1000
        assert client.get("/api/v1/display/current.jpg", headers={"If-None-Match": image.headers["etag"]}).status_code == 304
        assert metadata["species"][0]["common_name"] == "Eurasian Blackbird"


def test_display_api_token_is_separate_from_settings_secrets(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        settings = client.get("/api/v1/settings").json()
        settings.update({"display_api_require_token": True, "display_api_token": "this-is-a-long-display-token"})
        saved = client.put("/api/v1/settings", json=settings)
        assert saved.status_code == 200
        assert saved.json()["has_display_api_token"] is True
        assert "display_api_token" not in saved.json()
        assert client.get("/api/v1/display/current.jpg").status_code == 401
        assert client.get("/api/v1/display/current.jpg?token=this-is-a-long-display-token").status_code == 200


def test_public_birdweather_station_id_is_saved_without_a_secret(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        settings = client.get("/api/v1/settings").json()
        settings.update({"detection_source": "birdweather_public", "birdweather_public_station_id": 2505})
        saved = client.put("/api/v1/settings", json=settings)
        assert saved.status_code == 200
        assert saved.json()["detection_source"] == "birdweather_public"
        assert saved.json()["birdweather_public_station_id"] == 2505
        assert saved.json()["has_birdweather_token"] is False


def test_settings_survive_application_restart(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        settings = client.get("/api/v1/settings").json()
        settings.update({
            "location_label": "Oslo, Norway",
            "detection_source": "birdweather_public",
            "birdweather_public_station_id": 2505,
            "tv_host": "192.168.1.134",
            "openrouter_api_key": "sk-or-v1-persistent-test-key",
        })
        assert client.put("/api/v1/settings", json=settings).status_code == 200

    restarted = create_app(tmp_path)
    with TestClient(restarted) as client:
        saved = client.get("/api/v1/settings").json()
        assert saved["location_label"] == "Oslo, Norway"
        assert saved["birdweather_public_station_id"] == 2505
        assert saved["tv_host"] == "192.168.1.134"
        assert saved["has_openrouter_api_key"] is True


def test_settings_activity_is_available_in_the_web_log(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        settings = client.get("/api/v1/settings").json()
        assert client.put("/api/v1/settings", json=settings).status_code == 200
        logs = client.get("/api/v1/logs").json()
        assert any("Settings saved" in entry["message"] for entry in logs)
