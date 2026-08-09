import socket
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from birdframe import main as birdframe_main
from birdframe.adapters import wake_on_lan
from birdframe.main import create_app, in_quiet_hours
from birdframe.schemas import DetectionCreate, PublicSettings
from tests.helpers import authed


def _settings(client: TestClient, **updates) -> dict:
    settings = client.get("/api/v1/settings").json()
    settings.update(updates)
    return client.put("/api/v1/settings", json=settings).json()


def test_confidence_threshold_gates_artwork_but_keeps_history(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        _settings(client, confidence_threshold=0.9)
        low = client.post("/api/v1/detections", json={
            "common_name": "Quiet Finch", "scientific_name": "Fringilla quietus",
            "confidence": 0.4, "source_event_id": "low",
        })
        assert low.status_code == 201
        current = client.get("/api/v1/display/current.json").json()
        assert current["species"] == []
        high = client.post("/api/v1/detections", json={
            "common_name": "Loud Thrush", "scientific_name": "Turdus loudus",
            "confidence": 0.99, "source_event_id": "high",
        })
        assert high.status_code == 201
        current = client.get("/api/v1/display/current.json").json()
        assert [item["common_name"] for item in current["species"]] == ["Loud Thrush"]
        names = {item["common_name"] for item in client.get("/api/v1/detections").json()}
        assert names == {"Quiet Finch", "Loud Thrush"}
        recent = client.get("/api/v1/birds/recent").json()
        assert [item["common_name"] for item in recent] == ["Loud Thrush"]


def test_duplicate_cooldown_skips_rerender_for_repeat_species(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        _settings(client, duplicate_cooldown_minutes=60)

        def revision() -> int:
            return client.get("/api/v1/compositions/current").json()["revision"]

        before = revision()
        client.post("/api/v1/detections", json={
            "common_name": "Common Swift", "scientific_name": "Apus apus",
            "confidence": 1.0, "source_event_id": "one",
        })
        after_first = revision()
        assert after_first > before
        second = client.post("/api/v1/detections", json={
            "common_name": "Common Swift", "scientific_name": "Apus apus",
            "confidence": 1.0, "source_event_id": "two",
        })
        assert second.status_code == 201
        assert revision() == after_first
        client.post("/api/v1/detections", json={
            "common_name": "Eurasian Magpie", "scientific_name": "Pica pica",
            "confidence": 1.0, "source_event_id": "three",
        })
        assert revision() > after_first


def test_display_exclusion_reason_distinguishes_confidence_and_cooldown(tmp_path):
    app = create_app(tmp_path)
    service = app.state.service
    low = DetectionCreate(common_name="Quiet Finch", scientific_name="Fringilla quietus", confidence=0.7)
    assert service.display_exclusion_reason(low) == "confidence 0.700 below threshold 0.800"
    service.store.add_detection(DetectionCreate(
        common_name="Common Swift", scientific_name="Apus apus", confidence=0.99,
        source_event_id="first-swift", detected_at=datetime.now(UTC),
    ))
    repeat = DetectionCreate(common_name="Common Swift", scientific_name="Apus apus", confidence=0.957)
    assert service.display_exclusion_reason(repeat) == "duplicate cooldown (5 min)"


def test_quiet_hours_window_overnight_and_timezone():
    base = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    overnight = PublicSettings(timezone="UTC", tv_quiet_hours_start="22:30", tv_quiet_hours_end="07:00")
    assert in_quiet_hours(overnight, base.replace(hour=23)) is True
    assert in_quiet_hours(overnight, base.replace(hour=3)) is True
    assert in_quiet_hours(overnight, base.replace(hour=12)) is False

    same_day = PublicSettings(timezone="UTC", tv_quiet_hours_start="13:00", tv_quiet_hours_end="14:00")
    assert in_quiet_hours(same_day, base.replace(hour=13, minute=30)) is True
    assert in_quiet_hours(same_day, base.replace(hour=14, minute=30)) is False

    assert in_quiet_hours(PublicSettings(tv_quiet_hours_start="", tv_quiet_hours_end="")) is False
    assert in_quiet_hours(PublicSettings(tv_quiet_hours_start="nope", tv_quiet_hours_end="07:00")) is False

    norway = PublicSettings(timezone="Europe/Oslo", tv_quiet_hours_start="22:00", tv_quiet_hours_end="06:00")
    assert in_quiet_hours(norway, datetime(2026, 7, 31, 21, 0, tzinfo=UTC)) is True
    assert in_quiet_hours(norway, datetime(2026, 7, 31, 14, 0, tzinfo=UTC)) is False


def test_wake_on_lan_sends_magic_packet_and_validates_mac():
    sent = []

    class FakeSocket:
        def __init__(self, family, kind):
            assert (family, kind) == (socket.AF_INET, socket.SOCK_DGRAM)

        def setsockopt(self, level, option, value):
            pass

        def sendto(self, data, address):
            sent.append((data, address))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch("birdframe.adapters.socket.socket", FakeSocket):
        wake_on_lan("AA:BB:CC:DD:EE:FF")
    payload, address = sent[0]
    assert payload == b"\xff" * 6 + bytes.fromhex("aabbccddeeff") * 16
    assert address == ("255.255.255.255", 9)

    with pytest.raises(ValueError):
        wake_on_lan("not-a-mac")


class FakeSamsung:
    """Test double for SamsungFrameClient; records uploads."""
    pushes: list[tuple[str, str, int]] = []

    def __init__(self, host: str, *, token: str | None = None, port: int = 8002, tv_factory=None, timeout: float | None = 60):
        self.host = host

    async def upload_and_select(self, image, *, file_type="JPG", matte="none", show=True):
        FakeSamsung.pushes.append((self.host, matte, len(image)))
        return type("Upload", (), {"content_id": f"FAKE{len(FakeSamsung.pushes)}"})()

    async def delete_owned(self, content_id):
        return None


@pytest.mark.asyncio
async def test_automatic_tv_sync_respects_quiet_hours_and_wakes(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        _settings(client, tv_host="10.0.0.3", tv_auto_update_enabled=True, tv_wake_enabled=True,
                  tv_mac="aa:bb:cc:dd:ee:ff", tv_update_minutes=1)
        client.post("/api/v1/detections", json={
            "common_name": "Common Swift", "scientific_name": "Apus apus",
            "confidence": 1.0, "source_event_id": "one",
        })
        service = app.state.service
        woken: list[str] = []
        monkeypatch.setattr(birdframe_main, "SamsungFrameClient", FakeSamsung)
        monkeypatch.setattr(birdframe_main, "wake_on_lan", lambda mac: woken.append(mac))

        now = datetime.now(UTC)
        _settings(client,
                  tv_quiet_hours_start=(now - timedelta(minutes=5)).strftime("%H:%M"),
                  tv_quiet_hours_end=(now + timedelta(minutes=5)).strftime("%H:%M"))
        FakeSamsung.pushes = []
        await service.sync_tv_if_due()
        assert FakeSamsung.pushes == []
        assert woken == []

        _settings(client, tv_quiet_hours_start="", tv_quiet_hours_end="")
        await service.sync_tv_if_due()
        assert woken == ["aa:bb:cc:dd:ee:ff"]
        assert len(FakeSamsung.pushes) == 1

        await service.sync_tv_if_due()
        assert len(FakeSamsung.pushes) == 1  # already uploaded the current revision


def test_tv_push_is_queued_as_a_background_job(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        _settings(client, tv_host="10.0.0.3")
        assert client.post("/api/v1/detections", json={
            "common_name": "Common Swift", "scientific_name": "Apus apus",
            "confidence": 1.0, "source_event_id": "push-one",
        }).status_code == 201
        monkeypatch.setattr(birdframe_main, "SamsungFrameClient", FakeSamsung)
        FakeSamsung.pushes = []
        response = client.post("/api/v1/tv/push")
        assert response.status_code == 202
        job_id = response.json()["id"]
        job = None
        for _ in range(30):
            job = next((item for item in client.get("/api/v1/jobs").json() if item["id"] == job_id), None)
            if job and job["status"] != "running":
                break
            time.sleep(0.1)
        assert job is not None
        assert job["kind"] == "tv_push"
        assert job["status"] == "completed"
        assert len(FakeSamsung.pushes) == 1
        logs = client.get("/api/v1/logs", params={"limit": 10}).json()
        assert any("TV push job" in entry["message"] for entry in logs)

@pytest.mark.asyncio
async def test_automatic_tv_sync_continues_when_wake_fails(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        _settings(client, tv_host="10.0.0.3", tv_auto_update_enabled=True, tv_wake_enabled=True,
                  tv_mac="bad-mac", tv_update_minutes=1)
        client.post("/api/v1/detections", json={
            "common_name": "Common Swift", "scientific_name": "Apus apus",
            "confidence": 1.0, "source_event_id": "one",
        })
        service = app.state.service
        monkeypatch.setattr(birdframe_main, "SamsungFrameClient", FakeSamsung)
        FakeSamsung.pushes = []
        await service.sync_tv_if_due()
        assert len(FakeSamsung.pushes) == 1
