import base64
import json

import httpx
import pytest

from birdframe.adapters import BIRDNET_GO_SSE_READ_TIMEOUT, BirdNETGoClient, BirdWeatherClient, OpenRouterClient, PublicBirdWeatherClient, SamsungFrameClient


def async_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")


@pytest.mark.asyncio
async def test_birdnet_sse_yields_detection_and_ignores_heartbeat():
    activity = []

    async def handler(request):
        assert request.headers["accept"] == "text/event-stream"
        return httpx.Response(200, content=(
            b"event: connected\ndata: {\"message\":\"ok\"}\n\n"
            b"event: heartbeat\ndata: {\"clients\":1}\n\n"
            b"event: detection\ndata: {\"id\":7,\"timestamp\":\"2026-01-02T03:04:05Z\",\"commonName\":\"Eurasian Blackbird\",\"scientificName\":\"Turdus merula\",\"confidence\":0.91}\n\n"
        ))
    client = async_client(handler)
    adapter = BirdNETGoClient("http://birdnet:8080", client=client, on_activity=activity.append)
    received = [item async for item in adapter.detections()]
    assert [(item.provider, item.external_id, item.common_name) for item in received] == [("birdnet-go", "7", "Eurasian Blackbird")]
    assert activity == ["connected", "heartbeat", "detection"]
    await client.aclose()


@pytest.mark.asyncio
async def test_birdnet_stream_health_checks_the_sse_endpoint():
    async def handler(request):
        assert request.url.path == "/api/v2/detections/stream"
        return httpx.Response(200, content=b"event: connected\ndata: {\"type\":\"detections\"}\n\n")

    client = async_client(handler)
    adapter = BirdNETGoClient("http://birdnet:8080", client=client)
    result = await adapter.stream_health()
    assert result.available is True
    assert result.detail == "detection stream connected"
    await client.aclose()


@pytest.mark.asyncio
async def test_birdnet_sse_allows_three_provider_heartbeat_intervals():
    adapter = BirdNETGoClient("http://birdnet:8080")
    assert adapter._client.timeout.read == BIRDNET_GO_SSE_READ_TIMEOUT
    await adapter.aclose()


@pytest.mark.asyncio
async def test_birdweather_polls_avian_cursor_and_normalizes_oldest_first():
    async def handler(request):
        assert request.url.path == "/api/v1/stations/a token/detections"
        assert dict(request.url.params) == {"limit": "10", "classification": "avian", "cursor": "40"}
        return httpx.Response(200, json={"success": True, "detections": [
            {"id": 42, "timestamp": "2026-01-02T10:00:00+00:00", "confidence": .8, "species": {"id": 2, "commonName": "Later", "scientificName": "Laterus birdus"}},
            {"id": 41, "timestamp": "2026-01-02T09:00:00+00:00", "confidence": .7, "species": {"id": 1, "commonName": "Earlier", "scientificName": "Earlierus birdus"}},
        ]})
    client = async_client(handler)
    result = await BirdWeatherClient("a token", base_url="http://test/api/v1", client=client).poll(cursor="40", limit=10)
    assert [item.common_name for item in result.detections] == ["Earlier", "Later"]
    assert result.cursor == "42"
    await client.aclose()


@pytest.mark.asyncio
async def test_public_birdweather_polls_a_public_station_without_a_token():
    async def handler(request):
        assert request.url.path == "/graphql"
        body = json.loads(request.content)
        assert body["variables"] == {"stationIds": ["2505"], "first": 10, "after": None}
        assert "classifications" in body["query"]
        return httpx.Response(200, json={"data": {"detections": {"nodes": [
            {"id": "42", "timestamp": "2026-01-02T10:00:00+00:00", "confidence": .8, "coords": {"lat": 59.9, "lon": 10.7}, "species": {"id": "2", "commonName": "Later", "scientificName": "Laterus birdus"}},
            {"id": "41", "timestamp": "2026-01-02T09:00:00+00:00", "confidence": .7, "coords": {"lat": 59.8, "lon": 10.6}, "species": {"id": "1", "commonName": "Earlier", "scientificName": "Earlierus birdus"}},
        ]}}})
    client = async_client(handler)
    result = await PublicBirdWeatherClient(2505, base_url="http://test/graphql", client=client).poll(limit=10)
    assert [(item.provider, item.external_id, item.common_name) for item in result.detections] == [("birdweather-public", "41", "Earlier"), ("birdweather-public", "42", "Later")]
    await client.aclose()


@pytest.mark.asyncio
async def test_public_birdweather_history_follows_graphql_cursors():
    requests = []
    async def handler(request):
        body = json.loads(request.content); requests.append(body["variables"])
        if body["variables"]["after"] is None:
            return httpx.Response(200, json={"data": {"detections": {"nodes": [
                {"id": "2", "timestamp": "2026-01-02T10:00:00+00:00", "confidence": .8, "coords": {}, "species": {"id": "2", "commonName": "Later", "scientificName": "Laterus birdus"}},
            ], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}})
        return httpx.Response(200, json={"data": {"detections": {"nodes": [
            {"id": "1", "timestamp": "2026-01-02T09:00:00+00:00", "confidence": .7, "coords": {}, "species": {"id": "1", "commonName": "Earlier", "scientificName": "Earlierus birdus"}},
        ], "pageInfo": {"hasNextPage": False, "endCursor": None}}}})
    client = async_client(handler)
    result = await PublicBirdWeatherClient(2505, base_url="http://test/graphql", client=client).history()
    assert [item.external_id for item in result.detections] == ["1", "2"]
    assert [item["after"] for item in requests] == [None, "next"]
    await client.aclose()


@pytest.mark.asyncio
async def test_openrouter_filters_image_models_and_decodes_generated_b64():
    async def handler(request):
        assert request.headers["authorization"] == "Bearer secret"
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json={"data": [
                {"id": "image/model", "name": "Image", "supported_parameters": ["size"], "pricing": {"image": "1"}},
                {"id": "text/model", "name": "Text", "supported_parameters": ["temperature"]},
            ]})
        assert request.url.path == "/api/v1/images"
        assert b'"model":"image/model"' in request.content
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"png bytes").decode(), "revised_prompt": "bird"}]})
    client = async_client(handler)
    adapter = OpenRouterClient("secret", base_url="http://test/api/v1", client=client)
    assert [model.id for model in await adapter.image_models()] == ["image/model"]
    image = await adapter.generate(model="image/model", prompt="a bird", size="1024x1024")
    assert image.content == b"png bytes" and image.revised_prompt == "bird"
    await client.aclose()


@pytest.mark.asyncio
async def test_samsung_upload_uses_art_mode_interface_without_library_import():
    events = []
    class Art:
        def upload(self, image, *, file_type, matte): events.append((image, file_type, matte)); return "MY_F0001"
        def select_image(self, content_id, *, show): events.append((content_id, show))
    class TV:
        def art(self): return Art()
    result = await SamsungFrameClient("10.0.0.3", tv_factory=lambda **kwargs: TV()).upload_and_select(b"jpeg", show=False)
    assert result.content_id == "MY_F0001"
    assert events == [(b"jpeg", "JPG", "none"), ("MY_F0001", False)]


@pytest.mark.asyncio
async def test_samsung_upload_only_switches_to_art_mode_when_already_active():
    class Art:
        def __init__(self, mode): self.mode = mode
        def upload(self, image, *, file_type, matte): return "MY_F0001"
        def get_artmode(self): return self.mode
        def select_image(self, content_id, *, show): self.shown = show
    class TV:
        def __init__(self, mode): self.artmode = mode
        def art(self): return Art(self.artmode)

    on = SamsungFrameClient("10.0.0.3", tv_factory=lambda **kwargs: TV("on"))
    result = await on.upload_and_select(b"jpeg")
    assert result.selected is True

    off = SamsungFrameClient("10.0.0.3", tv_factory=lambda **kwargs: TV("off"))
    result = await off.upload_and_select(b"jpeg")
    assert result.selected is False

    class BrokenArt(Art):
        def get_artmode(self): raise RuntimeError("tv busy")
    class BrokenTV:
        def art(self): return BrokenArt("on")
    broken = SamsungFrameClient("10.0.0.3", tv_factory=lambda **kwargs: BrokenTV())
    result = await broken.upload_and_select(b"jpeg")
    assert result.selected is False
