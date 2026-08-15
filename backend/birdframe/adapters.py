"""Network adapters for detection providers, image generation, and Frame TVs.

They are deliberately independent of FastAPI and persistence.  The application
can map :class:`Detection` and the result DTOs to its own database models.
"""
from __future__ import annotations

import asyncio
import base64
import json
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote, urljoin

import httpx


class AdapterError(RuntimeError): pass
class ProviderUnavailable(AdapterError): pass


@dataclass(frozen=True, slots=True)
class Detection:
    provider: str; external_id: str; occurred_at: datetime; common_name: str
    scientific_name: str | None; confidence: float | None
    species_code: str | None = None; latitude: float | None = None; longitude: float | None = None
    raw: dict[str, Any] | None = None

@dataclass(frozen=True, slots=True)
class Health:
    available: bool; detail: str | None = None

@dataclass(frozen=True, slots=True)
class PollResult:
    detections: tuple[Detection, ...]; cursor: str | None

@dataclass(frozen=True, slots=True)
class ImageModel:
    id: str; name: str; description: str | None; context_length: int | None
    pricing: dict[str, Any] | None; supported_parameters: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class GeneratedImage:
    content: bytes; media_type: str; revised_prompt: str | None = None

@dataclass(frozen=True, slots=True)
class SamsungUpload:
    content_id: str; selected: bool


BIRDNET_GO_SSE_READ_TIMEOUT = 90.0


def wake_on_lan(mac: str, *, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Send a Wake-on-LAN magic packet for a TV MAC address.

    Wake-on-LAN only ever wakes a sleeping device; it never turns a powered-on
    TV off, so it is safe to send before an automatic artwork update.
    """
    cleaned = mac.strip().replace("-", "").replace(":", "").replace(".", "")
    if len(cleaned) != 12:
        raise ValueError("TV MAC address must be 12 hexadecimal digits")
    try:
        address = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError("TV MAC address must be 12 hexadecimal digits") from exc
    packet = b"\xff" * 6 + address * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value: raise AdapterError("provider response is missing a timestamp")
    try: result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc: raise AdapterError(f"invalid provider timestamp: {value!r}") from exc
    if result.tzinfo is None: raise AdapterError("provider timestamp has no timezone")
    return result

def _float(value: Any) -> float | None:
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


class BirdNETGoClient:
    """Async consumer of BirdNET-Go's public ``detection`` SSE events."""
    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None,
                 on_activity: Callable[[str], None] | None = None) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(20, read=BIRDNET_GO_SSE_READ_TIMEOUT))
        self._owns = client is None
        self._on_activity = on_activity

    def _activity(self, kind: str) -> None:
        if self._on_activity:
            self._on_activity(kind)

    async def aclose(self) -> None:
        if self._owns: await self._client.aclose()
    async def health(self) -> Health:
        try:
            response = await self._client.get(urljoin(self.base_url, "api/v2/sse/status")); response.raise_for_status(); body = response.json()
            return Health(body.get("status") == "active", body.get("status"))
        except (httpx.HTTPError, ValueError) as exc: return Health(False, str(exc))

    async def stream_health(self) -> Health:
        """Verify that the detection SSE endpoint opens and emits an event."""
        try:
            async with self._client.stream("GET", urljoin(self.base_url, "api/v2/detections/stream"), headers={"Accept": "text/event-stream"}) as response:
                response.raise_for_status(); event = "message"
                async for line in response.aiter_lines():
                    if not line:
                        if event in {"connected", "heartbeat", "detection"}:
                            return Health(True, f"detection stream {event}")
                        event = "message"
                        continue
                    if line.startswith("event:"): event = line[6:].strip()
                return Health(False, "detection stream ended before sending an event")
        except (httpx.HTTPError, ValueError) as exc:
            return Health(False, str(exc))

    async def detections(self) -> AsyncIterator[Detection]:
        try:
            async with self._client.stream("GET", urljoin(self.base_url, "api/v2/detections/stream"), headers={"Accept": "text/event-stream"}) as response:
                response.raise_for_status(); self._activity("connected"); event, lines = "message", []
                async for line in response.aiter_lines():
                    if not line:
                        if event == "heartbeat":
                            self._activity("heartbeat")
                        elif event == "detection" and lines:
                            self._activity("detection")
                            yield self._parse(json.loads("\n".join(lines)))
                        event, lines = "message", []; continue
                    if line.startswith("event:"): event = line[6:].strip()
                    elif line.startswith("data:"): lines.append(line[5:].lstrip())
                if event == "detection" and lines:
                    self._activity("detection")
                    yield self._parse(json.loads("\n".join(lines)))
        except (httpx.HTTPError, json.JSONDecodeError) as exc: raise AdapterError(f"BirdNET-Go stream failed: {exc}") from exc
    @staticmethod
    def _parse(data: dict[str, Any]) -> Detection:
        name = data.get("commonName")
        if not isinstance(name, str) or not name: raise AdapterError("BirdNET-Go detection misses commonName")
        timestamp = _timestamp(data.get("timestamp") or data.get("beginTime"))
        return Detection("birdnet-go", str(data.get("id") or f"{name}:{timestamp.isoformat()}"), timestamp, name, data.get("scientificName"), _float(data.get("confidence")), data.get("speciesCode"), _float(data.get("latitude")), _float(data.get("longitude")), data)


class BirdWeatherClient:
    """Read-only, cursor-based BirdWeather station poller."""
    def __init__(self, station_token: str, *, base_url: str = "https://app.birdweather.com/api/v1/", client: httpx.AsyncClient | None = None) -> None:
        if not station_token: raise ValueError("station token is required")
        self.station_token = station_token; self.base_url = base_url.rstrip("/") + "/"; self._client = client or httpx.AsyncClient(timeout=20); self._owns = client is None
    async def aclose(self) -> None:
        if self._owns: await self._client.aclose()
    @property
    def url(self) -> str: return urljoin(self.base_url, f"stations/{quote(self.station_token, safe='')}/detections")
    async def health(self) -> Health:
        try:
            response = await self._client.get(self.url, params={"limit": 1, "classification": "avian"}); response.raise_for_status(); body = response.json()
            return Health(bool(body.get("success", True)))
        except (httpx.HTTPError, ValueError) as exc: return Health(False, str(exc))
    async def poll(self, *, cursor: str | None = None, limit: int = 100) -> PollResult:
        if not 1 <= limit <= 100: raise ValueError("limit must be from 1 to 100")
        params: dict[str, str | int] = {"limit": limit, "classification": "avian"}
        if cursor: params["cursor"] = cursor
        try:
            response = await self._client.get(self.url, params=params); response.raise_for_status(); body = response.json()
        except (httpx.HTTPError, ValueError) as exc: raise AdapterError(f"BirdWeather polling failed: {exc}") from exc
        if body.get("success") is False: raise AdapterError("BirdWeather rejected the station request")
        rows = body.get("detections", [])
        if not isinstance(rows, list): raise AdapterError("BirdWeather response has invalid detections")
        detections = tuple(sorted((self._parse(row) for row in rows), key=lambda item: item.occurred_at))
        ids = [int(item.external_id) for item in detections if item.external_id.isdigit()]
        return PollResult(detections, str(max(ids)) if ids else cursor)
    @staticmethod
    def _parse(data: dict[str, Any]) -> Detection:
        species = data.get("species") if isinstance(data.get("species"), dict) else data; name = species.get("commonName")
        if not isinstance(name, str) or not name: raise AdapterError("BirdWeather detection misses species.commonName")
        timestamp = _timestamp(data.get("timestamp"))
        return Detection("birdweather", str(data.get("id") or f"{name}:{timestamp.isoformat()}"), timestamp, name, species.get("scientificName"), _float(data.get("confidence")), str(species["id"]) if species.get("id") is not None else None, _float(data.get("lat")), _float(data.get("lon")), data)


class PublicBirdWeatherClient:
    """Read recent avian detections from a public BirdWeather station.

    BirdWeather's GraphQL API exposes public station data by numeric station ID;
    unlike the REST station endpoints it does not require the station owner's
    authentication token.  We deliberately re-read the small latest window on
    every poll and rely on the application's source-event de-duplication.  A
    Relay cursor would advance into older rows after the first poll and miss
    newly arriving detections in the default newest-first ordering.
    """

    QUERY = """
    query PublicStationDetections($stationIds: [ID!], $first: Int, $after: String) {
      detections(first: $first, after: $after, stationIds: $stationIds, classifications: [\"avian\"]) {
        nodes {
          id timestamp confidence
          coords { lat lon }
          species { id commonName scientificName }
        }
        pageInfo { endCursor hasNextPage }
      }
    }
    """

    def __init__(self, station_id: int, *, base_url: str = "https://app.birdweather.com/graphql", client: httpx.AsyncClient | None = None) -> None:
        if station_id < 1:
            raise ValueError("public station ID must be positive")
        self.station_id = station_id
        self.base_url = base_url
        self._client = client or httpx.AsyncClient(timeout=20)
        self._owns = client is None

    async def aclose(self) -> None:
        if self._owns:
            await self._client.aclose()

    async def health(self) -> Health:
        try:
            await self.poll(limit=1)
            return Health(True)
        except AdapterError as exc:
            return Health(False, str(exc))

    async def poll(self, *, limit: int = 100, after: str | None = None) -> PollResult:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be from 1 to 100")
        try:
            response = await self._client.post(self.base_url, json={"query": self.QUERY, "variables": {"stationIds": [str(self.station_id)], "first": limit, "after": after}})
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterError(f"Public BirdWeather polling failed: {exc}") from exc
        errors = body.get("errors")
        if errors:
            detail = errors[0].get("message", "GraphQL query failed") if isinstance(errors, list) and errors and isinstance(errors[0], dict) else "GraphQL query failed"
            raise AdapterError(f"Public BirdWeather rejected the station request: {detail}")
        connection = body.get("data", {}).get("detections", {}) if isinstance(body.get("data"), dict) else {}
        rows = connection.get("nodes", []) if isinstance(connection, dict) else []
        if not isinstance(rows, list):
            raise AdapterError("Public BirdWeather response has invalid detections")
        detections = tuple(sorted((self._parse(row) for row in rows), key=lambda item: item.occurred_at))
        page_info = connection.get("pageInfo", {}) if isinstance(connection, dict) else {}
        cursor = page_info.get("endCursor") if isinstance(page_info, dict) and page_info.get("hasNextPage") else None
        return PollResult(detections, cursor if isinstance(cursor, str) else None)

    async def history(self, *, max_results: int = 2000) -> PollResult:
        """Fetch the public station's complete default 24-hour window.

        BirdWeather's public GraphQL query defaults to the last 24 hours.
        Cursor paging is used only for this startup seed; live polling keeps
        requesting the newest page so new detections are never skipped.
        """
        if max_results < 1:
            raise ValueError("max_results must be positive")
        cursor: str | None = None
        collected: list[Detection] = []
        while len(collected) < max_results:
            page = await self.poll(limit=min(100, max_results - len(collected)), after=cursor)
            collected.extend(page.detections)
            if not page.cursor:
                break
            cursor = page.cursor
        return PollResult(tuple(sorted(collected, key=lambda item: item.occurred_at)), None)

    @staticmethod
    def _parse(data: dict[str, Any]) -> Detection:
        species = data.get("species") if isinstance(data.get("species"), dict) else {}
        name = species.get("commonName")
        if not isinstance(name, str) or not name:
            raise AdapterError("Public BirdWeather detection misses species.commonName")
        coords = data.get("coords") if isinstance(data.get("coords"), dict) else {}
        timestamp = _timestamp(data.get("timestamp"))
        return Detection("birdweather-public", str(data.get("id") or f"{name}:{timestamp.isoformat()}"), timestamp, name, species.get("scientificName"), _float(data.get("confidence")), str(species["id"]) if species.get("id") is not None else None, _float(coords.get("lat")), _float(coords.get("lon")), data)


class OpenRouterClient:
    """Client for OpenRouter model catalog and dedicated image endpoint."""
    def __init__(self, api_key: str, *, base_url: str = "https://openrouter.ai/api/v1/", client: httpx.AsyncClient | None = None) -> None:
        if not api_key: raise ValueError("OpenRouter API key is required")
        self.base_url = base_url.rstrip("/") + "/"; self._client = client or httpx.AsyncClient(timeout=120); self._owns = client is None
        self._headers = {"Authorization": f"Bearer {api_key}"}
    async def aclose(self) -> None:
        if self._owns: await self._client.aclose()
    async def image_models(self) -> tuple[ImageModel, ...]:
        try:
            response = await self._client.get(urljoin(self.base_url, "models"), headers=self._headers); response.raise_for_status(); rows = response.json().get("data", [])
        except (httpx.HTTPError, ValueError) as exc: raise AdapterError(f"OpenRouter model lookup failed: {exc}") from exc
        models = []
        for row in rows:
            params = tuple(row.get("supported_parameters") or ())
            # Catalog semantics evolve.  Include known image capable entries only.
            modalities = row.get("architecture", {}).get("output_modalities") or []
            if any(p in {"images", "image_generation", "size", "quality"} for p in params) or "image" in modalities:
                models.append(ImageModel(row["id"], row.get("name", row["id"]), row.get("description"), row.get("context_length"), row.get("pricing"), params))
        return tuple(models)
    async def generate(self, *, model: str, prompt: str, size: str | None = None, quality: str | None = None) -> GeneratedImage:
        payload: dict[str, Any] = {"model": model, "prompt": prompt}
        if size: payload["size"] = size
        if quality: payload["quality"] = quality
        try:
            response = await self._client.post(urljoin(self.base_url, "images"), headers=self._headers, json=payload); response.raise_for_status(); body = response.json()
        except (httpx.HTTPError, ValueError) as exc: raise AdapterError(f"OpenRouter image generation failed: {exc}") from exc
        images = body.get("data") or body.get("images") or []
        if not images: raise AdapterError("OpenRouter returned no generated image")
        image = images[0]; revised = image.get("revised_prompt") or body.get("revised_prompt")
        if image.get("b64_json"):
            try: return GeneratedImage(base64.b64decode(image["b64_json"], validate=True), "image/png", revised)
            except ValueError as exc: raise AdapterError("OpenRouter returned malformed image data") from exc
        if image.get("url"):
            try:
                download = await self._client.get(image["url"], follow_redirects=False); download.raise_for_status()
                return GeneratedImage(download.content, download.headers.get("content-type", "image/png").split(";", 1)[0], revised)
            except httpx.HTTPError as exc: raise AdapterError(f"OpenRouter image download failed: {exc}") from exc
        raise AdapterError("OpenRouter response had neither image data nor URL")


class SamsungFrameClient:
    """Async facade over optional synchronous ``samsungtvws`` Art Mode support."""
    def __init__(self, host: str, *, token: str | None = None, port: int = 8002, tv_factory: Callable[..., Any] | None = None, timeout: float | None = 60) -> None:
        self.host, self.token, self.port, self._factory, self.timeout = host, token, port, tv_factory, timeout
    def _tv(self) -> Any:
        if self._factory: return self._factory(host=self.host, token=self.token, port=self.port)
        try:
            from samsungtvws import SamsungTVWS
        except ImportError as exc: raise ProviderUnavailable("Samsung support requires the samsungtvws extra") from exc
        return SamsungTVWS(host=self.host, token=self.token, port=self.port, timeout=self.timeout)
    async def upload_and_select(self, image: bytes, *, file_type: str = "JPG", matte: str = "none", show: bool = True) -> SamsungUpload:
        if not image: raise ValueError("cannot upload an empty image")
        def operation() -> SamsungUpload:
            tv = self._tv(); art = tv.art(); content_id = art.upload(image, file_type=file_type, matte=matte)
            show_now = False
            if show:
                # Only force Art Mode if the TV is already showing it. When the
                # family is watching TV, upload + select quietly so the new
                # composition is ready but the screen is not interrupted.
                try:
                    show_now = str(art.get_artmode()).lower() in ("on", "true", "1")
                except Exception:
                    show_now = False
            art.select_image(content_id, show=show_now)
            return SamsungUpload(str(content_id), show_now)
        try: return await asyncio.to_thread(operation)
        except ProviderUnavailable: raise
        except Exception as exc: raise AdapterError(f"Samsung artwork upload failed: {exc}") from exc
    async def delete_owned(self, content_id: str) -> None:
        """Delete only a content id BirdFrame previously recorded as its own."""
        if not content_id:
            return
        def operation() -> None:
            self._tv().art().delete(content_id)
        try: await asyncio.to_thread(operation)
        except ProviderUnavailable: raise
        except Exception as exc: raise AdapterError(f"Samsung artwork delete failed: {exc}") from exc
