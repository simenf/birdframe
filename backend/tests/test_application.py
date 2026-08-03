from pathlib import Path
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from birdframe.main import create_app
from birdframe.schemas import DetectionCreate
from birdframe.storage import Store
from tests.helpers import authed


def test_detection_generates_identical_current_display_artifact(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        settings = client.get("/api/v1/settings").json()
        settings.update({"output_width": 640, "output_height": 360, "display_api_enabled": True, "collage_style": "avianvisitors_horizontal"})
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
        authed(client)
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
        authed(client)
        settings = client.get("/api/v1/settings").json()
        settings.update({"detection_source": "birdweather_public", "birdweather_public_station_id": 2505})
        saved = client.put("/api/v1/settings", json=settings)
        assert saved.status_code == 200
        assert saved.json()["detection_source"] == "birdweather_public"
        assert saved.json()["birdweather_public_station_id"] == 2505
        assert saved.json()["has_birdweather_token"] is False


def test_recent_birds_are_deduplicated_and_include_an_image(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        for identifier, common_name, scientific_name in (("one", "Common Swift", "Apus apus"), ("two", "Common Swift", "Apus apus"), ("three", "Eurasian Magpie", "Pica pica")):
            assert client.post("/api/v1/detections", json={
                "common_name": common_name, "scientific_name": scientific_name,
                "source_type": "manual", "source_event_id": identifier,
            }).status_code == 201
        birds = client.get("/api/v1/birds/recent").json()
        assert [(bird["common_name"], bird["count"]) for bird in birds] == [("Common Swift", 2), ("Eurasian Magpie", 1)]
        assert "/api/v1/birds/image.png?" in birds[0]["image_url"]
        assert all(bird["has_artwork"] is False for bird in birds)
        assert client.get(birds[0]["image_url"]).headers["content-type"] == "image/png"


def test_recent_birds_report_artwork_once_a_species_asset_exists(tmp_path: Path):
    from PIL import Image

    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        assert client.post("/api/v1/detections", json={
            "common_name": "Eurasian Magpie", "scientific_name": "Pica pica",
            "source_type": "manual", "source_event_id": "magpie",
        }).status_code == 201
        birds = client.get("/api/v1/birds/recent").json()
        assert birds[0]["has_artwork"] is False

        target = tmp_path / "art" / "species" / "pica-pica"
        target.mkdir(parents=True)
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(target / "perched.png")

        birds = client.get("/api/v1/birds/recent").json()
        assert birds[0]["has_artwork"] is True


def test_occurrences_report_which_species_are_missing_artwork(tmp_path: Path):
    from PIL import Image

    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        for identifier, common_name, scientific_name in (("swift", "Common Swift", "Apus apus"), ("magpie", "Eurasian Magpie", "Pica pica")):
            assert client.post("/api/v1/detections", json={
                "common_name": common_name, "scientific_name": scientific_name,
                "source_type": "manual", "source_event_id": identifier,
            }).status_code == 201
        occurrences = client.get("/api/v1/art/occurrences").json()
        assert {item["common_name"]: item["has_artwork"] for item in occurrences} == {
            "Common Swift": False, "Eurasian Magpie": False,
        }

        target = tmp_path / "art" / "species" / "pica-pica"
        target.mkdir(parents=True)
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(target / "perched.png")

        occurrences = client.get("/api/v1/art/occurrences").json()
        assert {item["common_name"]: item["has_artwork"] for item in occurrences} == {
            "Common Swift": False, "Eurasian Magpie": True,
        }


def test_journal_display_mode_renders_a_journal_page(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        settings = client.get("/api/v1/settings").json()
        settings.update({"display_mode": "journal"})
        assert client.put("/api/v1/settings", json=settings).status_code == 200
        for identifier, common_name, scientific_name in (
            ("j1", "Common Swift", "Apus apus"),
            ("j2", "Eurasian Magpie", "Pica pica"),
            ("j3", "Great Tit", "Parus major"),
            ("j4", "European Robin", "Erithacus rubecula"),
        ):
            assert client.post("/api/v1/detections", json={
                "common_name": common_name, "scientific_name": scientific_name,
                "source_type": "manual", "source_event_id": identifier,
            }).status_code == 201
        current = client.get("/api/v1/display/current.json").json()
        assert current["mode"] == "journal"
        assert [item["common_name"] for item in current["species"]] == [
            "Common Swift", "Eurasian Magpie", "Great Tit", "European Robin",
        ]
        jpg = client.get("/api/v1/display/current.jpg")
        assert jpg.status_code == 200
        assert jpg.headers["content-type"] == "image/jpeg"


def test_journal_counts_only_from_local_midnight(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        settings = client.get("/api/v1/settings").json()
        settings.update({"display_mode": "journal", "timezone": "UTC"})
        assert client.put("/api/v1/settings", json=settings).status_code == 200
        now = datetime.now(UTC)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        assert client.post("/api/v1/detections", json={
            "common_name": "Eurasian Magpie", "scientific_name": "Pica pica",
            "confidence": 0.99, "source_event_id": "yesterday-evening",
            "detected_at": (midnight - timedelta(hours=2)).isoformat(),
        }).status_code == 201
        assert client.post("/api/v1/detections", json={
            "common_name": "Common Swift", "scientific_name": "Apus apus",
            "confidence": 0.99, "source_event_id": "today",
            "detected_at": now.isoformat(),
        }).status_code == 201
        current = client.get("/api/v1/display/current.json").json()
        assert [item["common_name"] for item in current["species"]] == ["Common Swift"]


def test_detections_since_has_no_500_row_cap(tmp_path: Path):
    store = Store(tmp_path)
    now = datetime.now(UTC)
    for index in range(520):
        assert store.add_detection(DetectionCreate(
            common_name="Common Swift", scientific_name="Apus apus",
            confidence=0.99, source_event_id=f"cap-{index}",
            detected_at=now - timedelta(seconds=index),
        )) is not None
    rows = store.detections_since(now.replace(hour=0, minute=0, second=0, microsecond=0), min_confidence=0.9)
    assert len(rows) == 520
    assert {row.scientific_name for row in rows} == {"Apus apus"}


def test_settings_survive_application_restart(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        settings = client.get("/api/v1/settings").json()
        settings.update({
            "location_label": "Oslo, Norway",
            "detection_source": "birdweather_public",
            "birdweather_public_station_id": 2505,
            "tv_host": "192.168.1.134",
            "collage_style": "avianvisitors_horizontal",
            "legend_script_size": "large",
            "openrouter_api_key": "test-openrouter-key",
        })
        assert client.put("/api/v1/settings", json=settings).status_code == 200

    restarted = create_app(tmp_path)
    with TestClient(restarted) as client:
        authed(client)
        saved = client.get("/api/v1/settings").json()
        assert saved["location_label"] == "Oslo, Norway"
        assert saved["birdweather_public_station_id"] == 2505
        assert saved["tv_host"] == "192.168.1.134"
        assert saved["collage_style"] == "avianvisitors_horizontal"
        assert saved["legend_script_size"] == "large"
        assert saved["has_openrouter_api_key"] is True


def test_settings_activity_is_available_in_the_web_log(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        settings = client.get("/api/v1/settings").json()
        assert client.put("/api/v1/settings", json=settings).status_code == 200
        logs = client.get("/api/v1/logs").json()
        assert any("Settings saved" in entry["message"] for entry in logs)


def test_health_reports_needs_setup_until_settings_are_saved(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        assert client.get("/api/v1/health").json()["needs_setup"] is True
        settings = client.get("/api/v1/settings").json()
        assert client.put("/api/v1/settings", json=settings).status_code == 200
        assert client.get("/api/v1/health").json()["needs_setup"] is False
