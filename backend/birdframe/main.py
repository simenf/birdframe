from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
import logging
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .adapters import AdapterError, BirdNETGoClient, BirdWeatherClient, OpenRouterClient, ProviderUnavailable, PublicBirdWeatherClient, SamsungFrameClient
from .compositor import SpeciesCount, collage_image, group_detections, latest_visitor_image, load_species_asset
from .packages import MAX_ARCHIVE_BYTES, PackageError, SAFE_ID, fetch_catalog, install_archive, install_package, install_package_url
from .schemas import (CompositionSummary, Detection, DetectionCreate, JobRequest, PackageInstallRequest,
                      PackageUrlInstallRequest, PublicSettings, SettingsResponse, SettingsUpdate, SourceTestRequest)
from .storage import Store

logger = logging.getLogger("birdframe")


def data_directory() -> Path:
    # Docker sets /data explicitly.  A workspace-relative default keeps imports,
    # tests, and local development from trying to create a root-owned directory.
    return Path(os.environ.get("BIRDFRAME_DATA_DIR", "./data"))


def frontend_directory() -> Path:
    return Path(os.environ.get("BIRDFRAME_FRONTEND_DIST", "/app/frontend-dist"))


def composition_summary(row: dict[str, Any]) -> CompositionSummary:
    return CompositionSummary(
        id=row["id"], revision=row["revision"], created_at=datetime.fromisoformat(row["created_at"]),
        mode=row["mode"], width=row["width"], height=row["height"], sha256=row["sha256"],
        species=row["species"], tv_confirmed=row["tv_confirmed"],
    )


def remove_paper_background(image: Image.Image, paper: str = "#f2e4c9") -> Image.Image:
    """Conservative local chroma-key fallback for images generated on a uniform cream ground."""
    image = image.convert("RGBA")
    paper = paper.lstrip("#")
    target = tuple(int(paper[index:index + 2], 16) for index in (0, 2, 4))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            distance = abs(red - target[0]) + abs(green - target[1]) + abs(blue - target[2])
            if distance < 42:
                pixels[x, y] = (red, green, blue, 0)
            elif distance < 84:
                pixels[x, y] = (red, green, blue, int(alpha * (distance - 42) / 42))
    return image


def style_prompt(common_name: str, scientific_name: str, pose: str, addendum: str) -> str:
    return f"""Generate a {pose} {common_name} ({scientific_name}) in the style of an Edo-period Japanese kachō-e woodblock print. Render with very few marks: two to four flat color zones with sharp boundaries, confident sumi-e ink linework, and soft watercolor washes. Use an earthy restrained palette of burnt umber, ochre, indigo, vermillion, and muted greens. Keep eye, beak, and feet crisp in ink. Match diagnostic field marks and proportions of this exact species.

Use one consistent warm cream aged-mulberry-paper ground filling the entire image. No branch, twig, perch, foliage, scenery, border, caption, signature, text, watermark, or shadow. The perch is implied by toe posture and never drawn. The whole bird must fit inside the frame with generous padding. Exactly two wings, two legs, one head, one beak, and one tail. For perched pose use one folded wing and visible small feet; for flight use two naturally extended wings and tucked or swept-back feet.

{addendum.strip()}""".strip()


class BirdFrameService:
    def __init__(self, store: Store):
        self.store = store
        self.events: set[asyncio.Queue[int]] = set()
        self.render_lock = asyncio.Lock()
        self.tv_lock = asyncio.Lock()

    def log(self, level: str, message: str) -> None:
        self.store.log(level, message)
        getattr(logger, level.lower(), logger.info)(message)

    async def render(self) -> dict[str, Any]:
        async with self.render_lock:
            settings = self.store.get_settings()
            detections = self.store.recent_detections(settings.collage_hours)
            grouped = group_detections(detections)
            if settings.display_mode == "latest_visitor":
                image, species = latest_visitor_image(grouped, settings, self.store.art_dir)
            else:
                image, species = collage_image(grouped, settings, self.store.art_dir)
            temporary = self.store.art_dir / f"composition-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.jpg"
            image.save(temporary, "JPEG", quality=94, subsampling=0, optimize=True)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            identifier = self.store.add_composition(mode=settings.display_mode, width=image.width, height=image.height,
                                                    path=temporary, sha256=digest, species=species)
            row = self.store.current_composition()
            assert row and row["id"] == identifier
            for queue in list(self.events):
                queue.put_nowait(row["revision"])
            return row

    async def ingest(self, payload: DetectionCreate, *, render: bool = True) -> Detection | None:
        result = self.store.add_detection(payload)
        if result and render:
            await self.render()
        return result

    async def push_to_tv(self, row: dict[str, Any] | None = None) -> dict[str, object]:
        """Upload and immediately select the composition in Samsung Art Mode."""
        settings = self.store.get_settings()
        if not settings.tv_host:
            raise AdapterError("Configure a Samsung TV host first")
        row = row or self.store.current_composition() or await self.render()
        async with self.tv_lock:
            tv = SamsungFrameClient(settings.tv_host, token=self.store.secret("samsung_token"))
            result = await tv.upload_and_select(Path(row["path"]).read_bytes(), matte=settings.tv_matte, show=True)
            previous = self.store.record_tv_upload(row["id"], result.content_id)
            deleted_previous = False
            if previous:
                try:
                    await tv.delete_owned(previous)
                    deleted_previous = True
                except AdapterError:
                    pass
            self.log("info", f"TV updated to composition revision {row['revision']} and selected in Art Mode")
            return {"content_id": result.content_id, "previous_owned_content_id": previous,
                    "deleted_previous": deleted_previous, "revision": row["revision"]}

    async def sync_tv_if_due(self) -> None:
        """Keep the Frame on the newest composition without polling the TV UI."""
        settings = self.store.get_settings()
        if not settings.tv_auto_update_enabled or not settings.tv_host:
            return
        row = self.store.current_composition()
        if not row:
            return
        previous = self.store.latest_tv_upload()
        if previous and previous["composition_id"] == row["id"]:
            return
        if previous:
            last_push = datetime.fromisoformat(previous["created_at"])
            elapsed = (datetime.now(UTC) - last_push.astimezone(UTC)).total_seconds()
            if elapsed < settings.tv_update_minutes * 60:
                return
        await self.push_to_tv(row)

    async def generate_assets(self, job_id: int, request: JobRequest) -> None:
        settings = self.store.get_settings()
        secret = self.store.secret("openrouter_api_key")
        if not secret:
            self.store.update_job(job_id, status="failed", error="Configure an OpenRouter API key first")
            self.log("warning", f"Artwork generation job {job_id} needs an OpenRouter API key")
            return
        model = request.model or settings.openrouter_model
        if not model:
            self.store.update_job(job_id, status="failed", error="Choose an OpenRouter image model")
            self.log("warning", f"Artwork generation job {job_id} needs an OpenRouter image model")
            return
        self.store.update_job(job_id, status="running")
        self.log("info", f"Artwork generation job {job_id} started for {len(request.species)} species")
        client = OpenRouterClient(secret)
        generated: list[str] = []
        try:
            for entry in request.species:
                common = entry.get("common_name", "").strip()
                scientific = entry.get("scientific_name", "").strip() or common
                if not common:
                    continue
                slug = "".join(char.lower() if char.isalnum() else "-" for char in scientific).strip("-")
                target = self.store.art_dir / "species" / slug
                target.mkdir(parents=True, exist_ok=True)
                poses = ("perched", "in flight with wings spread") if request.poses == "both" else ("perched",)
                for requested_pose in poses:
                    response = await client.generate(model=model, prompt=style_prompt(common, scientific, requested_pose, settings.custom_prompt_addendum), size="1024x1024")
                    with Image.open(__import__("io").BytesIO(response.content)) as source:
                        asset = source.convert("RGBA")
                    if asset.getchannel("A").getextrema()[0] == 255:
                        asset = remove_paper_background(asset, settings.paper_tone)
                    pose_name = "flight" if requested_pose.startswith("in flight") else "perched"
                    asset.save(target / f"{pose_name}.png", "PNG", optimize=True)
                    generated.append(f"{common}:{pose_name}")
            self.store.update_job(job_id, status="completed", result={"generated": generated})
            self.log("info", f"Artwork generation job {job_id} completed: {len(generated)} assets saved")
            await self.render()
        except (AdapterError, OSError, ValueError) as exc:
            self.store.update_job(job_id, status="failed", error=str(exc))
            self.log("error", f"Artwork generation job {job_id} failed: {exc}")
        finally:
            await client.aclose()


async def source_worker(service: BirdFrameService, stop: asyncio.Event) -> None:
    """Conservative source worker; all ingest paths still share deduplication and rendering."""
    cursor: str | None = None
    last_source = ""

    async def pause(seconds: int) -> None:
        """Wait for a source poll interval without allowing its timeout to kill the worker."""
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    while not stop.is_set():
        settings = service.store.get_settings()
        if settings.detection_source != last_source:
            cursor, last_source = None, settings.detection_source
        try:
            if settings.detection_source == "birdweather":
                token = service.store.secret("birdweather_token")
                if token:
                    client = BirdWeatherClient(token)
                    result = await client.poll(cursor=cursor, limit=100)
                    cursor = result.cursor
                    changed = False
                    for item in result.detections:
                        created = service.store.add_detection(DetectionCreate(
                            common_name=item.common_name, scientific_name=item.scientific_name or "",
                            species_code=item.species_code or "", confidence=item.confidence or 0,
                            detected_at=item.occurred_at, source_type="birdweather", source_event_id=item.external_id,
                        ))
                        changed = changed or created is not None
                    await client.aclose()
                    if changed:
                        await service.render()
                        service.log("info", "Imported new detections from private BirdWeather station")
                await pause(settings.birdweather_poll_seconds)
            elif settings.detection_source == "birdweather_public":
                if settings.birdweather_public_station_id:
                    client = PublicBirdWeatherClient(settings.birdweather_public_station_id)
                    seeding = cursor is None
                    result = await client.history() if seeding else await client.poll(limit=100)
                    changed = False
                    for item in result.detections:
                        created = service.store.add_detection(DetectionCreate(
                            common_name=item.common_name, scientific_name=item.scientific_name or "",
                            species_code=item.species_code or "", confidence=item.confidence or 0,
                            detected_at=item.occurred_at, source_type="birdweather_public", source_event_id=item.external_id,
                        ))
                        changed = changed or created is not None
                    await client.aclose()
                    if changed:
                        await service.render()
                        activity = "Seeded the previous 24 hours" if seeding else "Imported new detections"
                        service.log("info", f"{activity} from public BirdWeather station {settings.birdweather_public_station_id}")
                    cursor = "live"
                await pause(settings.birdweather_poll_seconds)
            else:
                # Reconnect after each event so a source change is observed promptly.
                client = BirdNETGoClient(settings.birdnet_go_url)
                stream = client.detections()
                try:
                    item = await asyncio.wait_for(anext(stream), timeout=10)
                    await service.ingest(DetectionCreate(
                        common_name=item.common_name, scientific_name=item.scientific_name or "",
                        species_code=item.species_code or "", confidence=item.confidence or 0,
                        detected_at=item.occurred_at, source_type="birdnet_go", source_event_id=item.external_id,
                    ))
                except TimeoutError:
                    pass
                finally:
                    await stream.aclose()
                    await client.aclose()
        except (AdapterError, OSError, asyncio.TimeoutError) as exc:
            service.log("warning", f"Detection source temporarily unavailable: {type(exc).__name__}")
            await pause(5)


async def tv_sync_worker(service: BirdFrameService, stop: asyncio.Event) -> None:
    """Select a newly rendered composition once the configured update cadence permits it."""
    while not stop.is_set():
        try:
            await service.sync_tv_if_due()
        except (AdapterError, OSError, ProviderUnavailable) as exc:
            service.log("warning", f"Automatic TV update deferred: {type(exc).__name__}")
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass


def create_app(data_dir: Path | None = None) -> FastAPI:
    store = Store(data_dir or data_directory())
    service = BirdFrameService(store)
    stop_sources = asyncio.Event()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if not store.current_composition():
            await service.render()
        worker = asyncio.create_task(source_worker(service, stop_sources))
        tv_worker = asyncio.create_task(tv_sync_worker(service, stop_sources))
        try:
            yield
        finally:
            stop_sources.set()
            worker.cancel()
            tv_worker.cancel()
            await asyncio.gather(worker, tv_worker, return_exceptions=True)

    app = FastAPI(title="BirdFrame", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.service = service
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def display_guard(request: Request) -> None:
        settings = store.get_settings()
        if not settings.display_api_enabled:
            raise HTTPException(status_code=404, detail="Display API is disabled")
        if settings.display_api_require_token:
            supplied = request.headers.get("Authorization", "").removeprefix("Bearer ") or request.query_params.get("token", "")
            if not supplied or supplied != store.secret("display_api_token"):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Display token is required")

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        current = store.current_composition()
        return {"status": "ok", "version": "0.1.0", "composition_revision": current["revision"] if current else None}

    @app.get("/api/v1/settings", response_model=SettingsResponse)
    async def get_settings() -> SettingsResponse:
        return store.get_settings()

    @app.put("/api/v1/settings", response_model=SettingsResponse)
    async def put_settings(payload: SettingsUpdate) -> SettingsResponse:
        result = store.save_settings(payload)
        service.log("info", f"Settings saved; active source is {result.detection_source}")
        await service.render()
        return result

    @app.get("/api/v1/detections", response_model=list[Detection])
    async def detections(hours: int = 24) -> list[Detection]:
        return store.recent_detections(max(1, min(hours, 8760)))

    @app.get("/api/v1/birds/recent")
    async def recent_birds(request: Request) -> list[dict[str, object]]:
        """One artwork-ready entry per species seen in the last 24 hours."""
        base = str(request.base_url).rstrip("/")
        return [
            {
                "common_name": item.common_name,
                "scientific_name": item.scientific_name,
                "count": item.count,
                "confidence": item.confidence,
                "latest_at": item.latest_at,
                "image_url": f"{base}/api/v1/birds/image.png?" + urlencode({
                    "common_name": item.common_name,
                    "scientific_name": item.scientific_name,
                    "revision": item.latest_at,
                }),
            }
            for item in group_detections(store.recent_detections(24, limit=5000))
        ]

    @app.get("/api/v1/birds/image.png")
    async def bird_image(common_name: str, scientific_name: str = "") -> Response:
        if not common_name.strip() or len(common_name) > 250 or len(scientific_name) > 250:
            raise HTTPException(status_code=422, detail="Invalid bird name")
        settings = store.get_settings()
        asset = load_species_asset(store.art_dir, SpeciesCount(
            common_name=common_name, scientific_name=scientific_name, count=1,
            confidence=1, latest_at="",
        ), "perched", settings.palette, settings.asset_pack_id, settings.asset_variant)
        asset.thumbnail((480, 480), Image.Resampling.LANCZOS)
        output = BytesIO()
        asset.save(output, "PNG", optimize=True)
        return Response(content=output.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/v1/art/packs")
    async def artwork_packs() -> list[dict[str, object]]:
        """List source-seeded and locally-installed compatible artwork packs."""
        root = store.art_dir / "packages"
        if not root.exists():
            return []
        result: list[dict[str, object]] = []
        for package in sorted(item for item in root.iterdir() if item.is_dir()):
            illustration = next((path for path in (package / "illustrations", package / "assets" / "illustrations", package / "avian" / "assets" / "illustrations") if path.is_dir()), None)
            sketches = next((path for path in (package / "sketches", package / "assets" / "sketches", package / "avian" / "assets" / "sketches") if path.is_dir()), None)
            if illustration or sketches:
                result.append({
                    "id": package.name,
                    "illustrations": len(list(illustration.glob("*.png"))) if illustration else 0,
                    "sketches": len(list(sketches.glob("*.png"))) if sketches else 0,
                })
        return result

    @app.post("/api/v1/detections", response_model=Detection, status_code=201)
    async def create_detection(payload: DetectionCreate) -> Detection:
        result = await service.ingest(payload)
        if result is None:
            raise HTTPException(status_code=409, detail="Duplicate source event")
        return result

    @app.post("/api/v1/compositions/rebuild", response_model=CompositionSummary)
    async def rebuild_composition() -> CompositionSummary:
        return composition_summary(await service.render())

    @app.get("/api/v1/compositions/current", response_model=CompositionSummary)
    async def current_composition() -> CompositionSummary:
        row = store.current_composition()
        if not row:
            row = await service.render()
        return composition_summary(row)

    @app.get("/api/v1/display/current.jpg", dependencies=[Depends(display_guard)])
    async def display_jpeg(request: Request) -> Response:
        row = store.current_composition() or await service.render()
        path = Path(row["path"])
        etag = f'"{row["sha256"]}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag, "X-BirdFrame-Revision": str(row["revision"])})
        return FileResponse(path, media_type="image/jpeg", headers={
            "ETag": etag, "X-BirdFrame-Revision": str(row["revision"]),
            "Cache-Control": "no-cache, must-revalidate",
        })

    @app.get("/api/v1/display/current.json", dependencies=[Depends(display_guard)])
    async def display_json(request: Request) -> dict[str, object]:
        row = store.current_composition() or await service.render()
        base = str(request.base_url).rstrip("/")
        # The display endpoint remains stable for TVs and other integrations,
        # while the revision query gives browsers a new cache key after rebuilds.
        return composition_summary(row).model_dump(mode="json") | {"image_url": f"{base}/api/v1/display/current.jpg?revision={row['revision']}"}

    @app.get("/api/v1/display/events", dependencies=[Depends(display_guard)])
    async def display_events() -> StreamingResponse:
        queue: asyncio.Queue[int] = asyncio.Queue()
        service.events.add(queue)
        async def stream() -> AsyncIterator[str]:
            try:
                current = store.current_composition()
                if current:
                    yield f"event: composition\ndata: {{\"revision\":{current['revision']}}}\n\n"
                while True:
                    revision = await queue.get()
                    yield f"event: composition\ndata: {{\"revision\":{revision}}}\n\n"
            finally:
                service.events.discard(queue)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/jobs")
    async def jobs() -> list[dict[str, object]]:
        return store.jobs()

    @app.get("/api/v1/logs")
    async def logs(limit: int = 100, offset: int | None = None) -> list[dict[str, object]] | dict[str, object]:
        page_size = max(1, min(limit, 100))
        page_offset = max(0, offset or 0)
        items, total = store.logs(page_size, page_offset)
        # Keep the original list response for small integrations that already
        # consume /logs. The new web pane requests offset=0 and receives page
        # metadata for navigation.
        if offset is None:
            return items
        return {"items": items, "total": total, "limit": page_size, "offset": page_offset}

    @app.post("/api/v1/sources/test")
    async def test_source(payload: SourceTestRequest) -> dict[str, object]:
        try:
            if payload.source == "birdweather":
                token = payload.token or store.secret("birdweather_token")
                if not token:
                    raise HTTPException(status_code=400, detail="Enter a BirdWeather station token")
                client = BirdWeatherClient(token)
            elif payload.source == "birdweather_public":
                station_id = payload.station_id or store.get_settings().birdweather_public_station_id
                if not station_id:
                    raise HTTPException(status_code=400, detail="Enter a public BirdWeather station ID")
                client = PublicBirdWeatherClient(station_id)
            else:
                settings = store.get_settings()
                client = BirdNETGoClient(payload.url or settings.birdnet_go_url)
            health = await client.health()
            await client.aclose()
            return {"available": health.available, "detail": health.detail}
        except AdapterError as exc:
            return {"available": False, "detail": str(exc)}

    @app.get("/api/v1/art/occurrences")
    async def occurrences() -> list[dict[str, object]]:
        settings = store.get_settings()
        # BirdWeather history is the zero-extra-dependency provider.  Scores are
        # intentionally labelled frequency rather than ecological probability.
        items = group_detections(store.recent_detections(24 * 365, limit=5000))
        maximum = max((item.count for item in items), default=1)
        return [{"common_name": item.common_name, "scientific_name": item.scientific_name,
                 "score": item.count / maximum, "score_label": "station_frequency", "detections": item.count}
                for item in items if item.count / maximum >= settings.occurrence_threshold][:settings.occurrence_max_species]

    @app.get("/api/v1/art/packages/catalog")
    async def package_catalog() -> list[dict[str, object]]:
        url = store.get_settings().package_catalog_url
        if not url:
            return []
        try:
            return await fetch_catalog(url)
        except PackageError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/v1/art/packages/install", status_code=202)
    async def package_install(payload: PackageInstallRequest) -> dict[str, int]:
        url = store.get_settings().package_catalog_url
        if not url:
            raise HTTPException(status_code=400, detail="Configure an artwork package catalog URL first")
        try:
            entries = await fetch_catalog(url)
        except PackageError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        entry = next((item for item in entries if item["id"] == payload.package_id), None)
        if not entry:
            raise HTTPException(status_code=404, detail="Package was not found in the configured catalog")
        job_id = store.create_job("package_install", {"package_id": payload.package_id})
        async def install() -> None:
            store.update_job(job_id, status="running")
            try:
                result = await install_package(entry, store.art_dir / "packages")
                store.update_job(job_id, status="completed", result=result)
                await service.render()
            except PackageError as exc:
                store.update_job(job_id, status="failed", error=str(exc))
        asyncio.create_task(install())
        return {"id": job_id}

    @app.post("/api/v1/art/packages/upload", status_code=202)
    async def package_upload(request: Request) -> dict[str, int]:
        """Queue a local ZIP package for safe installation.

        The browser sends the ZIP as the raw request body. This avoids requiring
        a multipart parser in the small Docker image.
        """
        filename = Path(request.headers.get("x-birdframe-filename", "package.zip")).name
        package_id = Path(filename).stem.lower()
        if not filename.lower().endswith(".zip") or not SAFE_ID.fullmatch(package_id):
            raise HTTPException(status_code=422, detail="ZIP filename must become a safe package id")
        temporary = Path(tempfile.mkdtemp(prefix="birdframe-upload-"))
        archive = temporary / "package.zip"
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_ARCHIVE_BYTES:
            shutil.rmtree(temporary, ignore_errors=True)
            raise HTTPException(status_code=413, detail="Package archive exceeds the 500 MB limit")
        body = await request.body()
        written = len(body)
        try:
            with archive.open("wb") as output:
                if written > MAX_ARCHIVE_BYTES:
                    raise HTTPException(status_code=413, detail="Package archive exceeds the 500 MB limit")
                output.write(body)
        except HTTPException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        job_id = store.create_job("package_upload", {"package_id": package_id, "filename": filename})
        async def install() -> None:
            store.update_job(job_id, status="running")
            try:
                result = install_archive(archive, package_id, store.art_dir / "packages")
                store.update_job(job_id, status="completed", result=result)
                await service.render()
            except (PackageError, OSError) as exc:
                store.update_job(job_id, status="failed", error=str(exc))
            finally:
                shutil.rmtree(temporary, ignore_errors=True)
        asyncio.create_task(install())
        return {"id": job_id}

    @app.post("/api/v1/art/packages/install-url", status_code=202)
    async def package_install_url(payload: PackageUrlInstallRequest) -> dict[str, int]:
        """Queue installation from a direct HTTPS ZIP URL."""
        from urllib.parse import urlparse
        parsed = urlparse(payload.url)
        package_id = payload.package_id or Path(parsed.path).stem.lower()
        if parsed.scheme != "https" or not parsed.netloc or not SAFE_ID.fullmatch(package_id):
            raise HTTPException(status_code=422, detail="Use an HTTPS ZIP URL and a safe package id")
        job_id = store.create_job("package_url_install", {"package_id": package_id, "url": payload.url})
        async def install() -> None:
            store.update_job(job_id, status="running")
            try:
                result = await install_package_url(payload.url, package_id, store.art_dir / "packages")
                store.update_job(job_id, status="completed", result=result)
                await service.render()
            except (PackageError, OSError) as exc:
                store.update_job(job_id, status="failed", error=str(exc))
        asyncio.create_task(install())
        return {"id": job_id}

    @app.post("/api/v1/art/generate", status_code=202)
    async def generate_art(payload: JobRequest) -> dict[str, int]:
        job_id = store.create_job("art_generation", payload.model_dump())
        asyncio.create_task(service.generate_assets(job_id, payload))
        return {"id": job_id}

    @app.get("/api/v1/openrouter/models")
    async def openrouter_models() -> list[dict[str, object]]:
        key = store.secret("openrouter_api_key")
        if not key:
            raise HTTPException(status_code=400, detail="Configure an OpenRouter API key first")
        client = OpenRouterClient(key)
        try:
            return [{"id": item.id, "name": item.name, "description": item.description,
                     "pricing": item.pricing, "supported_parameters": item.supported_parameters} for item in await client.image_models()]
        finally:
            await client.aclose()

    @app.post("/api/v1/tv/push")
    async def push_tv() -> dict[str, object]:
        try:
            return await service.push_to_tv()
        except ProviderUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AdapterError as exc:
            status_code = 400 if "Configure a Samsung TV host" in str(exc) else 502
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    static = frontend_directory()
    if static.exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")
        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str) -> Response:
            target = static / path
            if path and target.is_file():
                return FileResponse(target)
            return FileResponse(static / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        async def placeholder() -> JSONResponse:
            return JSONResponse({"name": "BirdFrame", "message": "Frontend build is not present yet", "docs": "/docs"})
    return app


app = create_app()
