import base64

import httpx
import pytest

from birdframe.adapters import BirdNETGoClient, BirdWeatherClient, OpenRouterClient, SamsungFrameClient


def async_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")


@pytest.mark.asyncio
async def test_birdnet_sse_yields_detection_and_ignores_heartbeat():
    async def handler(request):
        assert request.headers["accept"] == "text/event-stream"
        return httpx.Response(200, content=(
            b"event: connected\ndata: {\"message\":\"ok\"}\n\n"
            b"event: heartbeat\ndata: {\"clients\":1}\n\n"
            b"event: detection\ndata: {\"id\":7,\"timestamp\":\"2026-01-02T03:04:05Z\",\"commonName\":\"Eurasian Blackbird\",\"scientificName\":\"Turdus merula\",\"confidence\":0.91}\n\n"
        ))
    client = async_client(handler)
    adapter = BirdNETGoClient("http://birdnet:8080", client=client)
    received = [item async for item in adapter.detections()]
    assert [(item.provider, item.external_id, item.common_name) for item in received] == [("birdnet-go", "7", "Eurasian Blackbird")]
    await client.aclose()


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
