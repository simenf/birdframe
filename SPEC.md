# BirdFrame product and technical specification

Status: Product decisions incorporated; ready for implementation planning  
Date: 2026-07-29

## 1. Purpose

BirdFrame is a self-hosted hobby application that listens for bird detections and turns recent visitors into artwork displayed on a Samsung The Frame TV.

It supports two detection sources:

1. A local microphone analyzed by BirdNET-Go.
2. An existing BirdWeather station, requiring no microphone on the BirdFrame host.

The application has a local web interface for first-run setup, health monitoring, artwork management, and TV control. It is installed with Docker Compose on an always-on computer and supports 64-bit Linux on both ARM and x86.

## 2. Product goals

- Detect local birds continuously without sending microphone audio to an image-generation provider.
- Display either an evolving 16:9 bird collage or a full-screen latest-visitor composition on a Samsung Frame TV; the collage is the default.
- Serve the exact current display image through a stable HTTP API so other TVs, dashboards, and applications can use the same backend.
- Make initial setup possible from a browser without editing configuration files.
- Let the user use a local microphone or an existing BirdWeather station.
- Let the user select a geographic location used for detection filtering and regional art preparation.
- Let the user bring an OpenRouter API key and select a compatible image model at runtime.
- Let the user generate regional artwork or install a pre-generated regional package.
- Avoid bundling optional model weights in the BirdFrame application image.
- Keep deployment and maintenance appropriate for a hobby project.
- Persist settings, artwork, detections, and Samsung pairing tokens across container upgrades.
- Keep the project in git and provide enough documentation for another hobbyist to install and troubleshoot it.

## 3. Non-goals for the first release

- Scientific-grade verification of detections.
- Native discovery or remote control for televisions other than Samsung Frame models. Other displays consume the generic current-image API.
- Running on Windows or macOS as a production microphone host.
- Remote access over the public internet.
- A hosted BirdFrame cloud service.
- Mobile applications.
- Training or fine-tuning bird-recognition models.
- Commercial use unless the dependency and model licensing strategy is changed.
- Publishing audio to BirdWeather. BirdWeather is initially an input alternative, not an upload target.

## 4. Recommended user experience

### 4.1 First-run wizard

The first visit opens a resumable wizard:

1. **Welcome and privacy**
   - Explain which operations are local and which contact external services.
   - Show non-commercial licensing notice.
2. **Location**
   - Search for a place or enter latitude/longitude manually.
   - Show coordinates before saving.
   - Select display language and timezone.
3. **Detection source**
   - Choose Local microphone or BirdWeather.
   - Local microphone: list devices reported by BirdNET-Go, test live input, choose device, set confidence threshold, and show model status.
   - BirdWeather: enter a station token, test it, show station name/location and latest detection, then save it securely.
4. **Samsung Frame**
   - Discover compatible TVs on the LAN.
   - Show name, model, IP address, resolution, and Art Mode support when available.
   - Allow manual IP and optional MAC address entry.
   - Pair and ask the user to approve BirdFrame on the TV.
   - Upload and display a generated test image, then remove only that test image.
5. **Artwork**
   - Choose a pre-generated regional package or configure OpenRouter.
   - OpenRouter: enter/test key, fetch compatible image models and capabilities, choose model, quality, and budget guardrail.
   - Choose an occurrence-data source, probability threshold, season, and maximum number of species to prepare.
   - Review the ordered species list and estimated maximum cost before generation.
   - Preview the AvianVisitors-inspired kachō-e style and start a resumable background generation job.
6. **Display behavior**
   - Choose Collage or Latest visitor; Collage is the default.
   - Configure the collage time window, minimum detection confidence, duplicate cooldown, refresh cadence, quiet hours, and whether BirdFrame may wake the TV.
7. **Review**
   - Show connection health and configuration summary.
   - Start monitoring.

Secrets are never returned to the browser after being saved. The UI shows only whether a secret is configured and its last successful test time.

### 4.2 Main dashboard

The dashboard shows:

- Current TV artwork and the birds represented in it.
- Latest detections with species, time, confidence, and source.
- State of BirdNET-Go or BirdWeather, the TV, and the artwork library.
- Pending image generation/package download jobs and estimated/recorded cost where the provider reports it.
- Controls to pause TV updates, refresh now, regenerate the composition, and retry failed operations.
- A link to advanced BirdNET-Go administration for model and microphone diagnostics.

### 4.3 Settings

- Location and language.
- Detection source and confidence/cooldown policy.
- BirdNET-Go connection and optional-model status.
- BirdWeather token and polling interval.
- TV discovery, pairing, test, matte, wake, and quiet-hour behavior.
- OpenRouter credentials, model, supported generation options, concurrency, and spend limits.
- Regional generation controls: occurrence provider, season, probability threshold, maximum species, manual includes/excludes, and estimated cost.
- Artwork appearance: built-in kachō-e preset, paper tone, palette, density, pose mix, labels, custom prompt addendum, installed packages, jobs, and storage use.
- Display mode, collage window, current-image API access, and output resolution.
- Artwork-package catalog/repository URL, with a reset-to-project-default action.
- Data retention and diagnostics.

## 5. Display concepts

Version 1 supports both display modes and uses the same reviewed species assets for each.

### 5.1 Collage mode

The default is an evolving collage closely inspired by AvianVisitors:

- Each species has two transparent illustrations: perched and in flight.
- A 3840 × 2160 sRGB master canvas is rendered locally.
- The collage contains unique species from a configurable time window. Presets are 1 hour, 12 hours, 24 hours, 7 days, and all retained detections; the default is 24 hours.
- Detection count controls relative bird area. Confidence and recency may be optional secondary weights, but count is the default.
- Repeated detections increase a species' prominence rather than adding unlimited copies.
- The selected pose is stable for a composition revision and can be overridden per species.
- The renderer respects a configurable safe area so the TV bezel or matte does not obscure birds.
- The final upload and API image are the same high-quality JPEG at exactly 3840 × 2160. A 1920 × 1080 profile is available for Frame models that report Full HD.

The web version of the collage supports silhouette-accurate hover/click selection, pose switching, species details, and recent detection information. The TV image is art-first and has no text by default; labels are an optional appearance setting.

### 5.2 Collage layout algorithm

BirdFrame reimplements the AvianVisitors layout rather than copying its frontend:

1. Generate a compact binary silhouette mask for every normalized asset by downsampling its alpha channel, thresholding it, and bit-packing it.
2. Sort visible species by target area descending.
3. Place the largest bird near the center of mass.
4. Search outward on a center-out spiral for each remaining bird.
5. Permit image bounding boxes to overlap when their alpha masks do not.
6. Bias the search ellipse horizontally to create a landscape-friendly cluster.
7. Repack the complete collage whenever the species set, counts, time window, canvas, or appearance settings change.
8. If any tile is outside the safe viewport, shrink all birds by 7% and repack, up to ten attempts.

Sizing is normalized against a viewport area budget rather than clamped independently:

```text
score_i       = weighted_detection_count_i ^ 0.65
area_i        = viewport_area_budget * score_i / sum(all_scores)
width_i       = sqrt(area_i * asset_aspect_ratio_i)
height_i      = sqrt(area_i / asset_aspect_ratio_i)
```

The total bird-area budget varies between 28% and 46% of the safe viewport based on species count. The exponent, area-budget bounds, horizontal bias, mask resolution, spiral stride, safe margin, and pose balance are configurable advanced settings with tested defaults.

The packing algorithm must be deterministic for the same inputs and seed. Adding a species causes a full repack, but stable ordering and seed selection should minimize gratuitous visual movement.

### 5.3 Latest-visitor mode

Latest-visitor mode renders the most recent qualifying species as a single large 16:9 composition using its approved perched or flight asset, the same warm-paper background, and the same palette. It does not incur a new paid image-generation request for each detection.

Optional labels can show common name, scientific name, detection time, and confidence. They are off by default to preserve the AvianVisitors art style.

### 5.4 Refresh behavior

The composition is regenerated after a qualifying detection. Samsung uploads are rate-limited and coalesced; the proposed default is no more than one upload every five minutes. Wake-on-LAN, quiet hours, upload interval, and retry behavior are configurable in the web interface. Automatic wake is explicitly chosen during setup rather than silently enabled.

## 6. Bird detection architecture

### 6.1 Recommendation: BirdNET-Go sidecar

Use the official BirdNET-Go container as a separate Compose service instead of embedding BirdNET inference into BirdFrame.

Reasons:

- It supports real-time sound-card and RTSP capture, multi-architecture Docker images, location-based range filtering, confidence controls, a web dashboard, and operational diagnostics.
- It exposes a real-time Server-Sent Events stream at `GET /api/v2/detections/stream`.
- Its current default BirdNET v2.4 model is embedded upstream, so BirdFrame does not need to copy or redistribute model files in its own image.
- Its model gallery can install optional models after deployment.
- It isolates CPU-intensive, failure-prone audio inference from TV and artwork orchestration.

BirdFrame consumes BirdNET-Go's SSE stream and maps each event to a canonical detection record:

```text
id
source_type
source_event_id
detected_at
common_name
scientific_name
species_code
confidence
latitude
longitude
raw_metadata
```

The SSE connection reconnects with exponential backoff. A source event ID plus timestamp/species uniqueness constraint makes reconnects idempotent.

### 6.2 Model handling

- BirdFrame does not include model weights in its Docker image or git repository.
- The UI reports the model currently active in BirdNET-Go.
- If an optional model is needed, the user explicitly starts its upstream download and sees license, size, progress, checksum/status, and activation state.
- For the first release, advanced model installation may deep-link to or proxy BirdNET-Go's existing model gallery rather than reimplementing it.
- The default BirdNET model does not require a separate BirdFrame download because it is embedded in the upstream BirdNET-Go distribution.
- Optional ONNX-based models require a compatible BirdNET-Go image/runtime and must be capability-checked before presenting an Install button.

### 6.3 Detection policy

BirdFrame applies a second, display-specific policy after BirdNET-Go:

- Minimum confidence.
- Optional species include/exclude list.
- Duplicate cooldown per species.
- Maximum age for an event to affect today's artwork.
- Optional “repeat confirmation” rule before a low-confidence species is shown.

This policy does not alter BirdNET-Go's scientific/detection database; it only determines display events.

## 7. BirdWeather architecture

BirdWeather is an alternative detection adapter:

- The user supplies a BirdWeather station authentication token.
- BirdFrame validates the token using the station API.
- It polls `GET /api/v1/stations/{token}/detections` with `classification=avian`, a small limit, and a saved cursor/timestamp.
- Results are timestamp-descending; BirdFrame persists processed detection IDs to prevent duplicates.
- Requests use backoff and a conservative configurable interval, proposed as 15 seconds.
- BirdWeather audio is not downloaded by default.
- The token is encrypted at rest and redacted from logs.

The canonical detection pipeline after ingestion is identical to local BirdNET-Go events. Switching sources therefore does not invalidate artwork, history, or TV settings.

The first release allows exactly one active source at a time. Source switching is explicit and preserves history, but BirdFrame does not merge simultaneous microphone and BirdWeather streams.

## 8. Region and species selection

The canonical location is latitude, longitude, timezone, country, and a human-readable label. Exact coordinates remain local except when sent to a user-selected external service.

For local detection, BirdNET-Go's range filter uses latitude, longitude, and time of year to reject unlikely species.

For regional pre-generation, BirdFrame produces a finite, ranked species list from a user-selected occurrence provider:

1. **BirdNET-Go range filter:** available when the microphone sidecar is installed; uses its location/week likelihood scores.
2. **eBird region:** optional and closest to AvianVisitors; accepts an eBird API key and country/state/county region code.
3. **BirdWeather station history:** available without another model or API key when BirdWeather is the active source; ranks previously detected species using count and recency. Its score is labeled “station frequency,” not ecological probability.

The settings page controls:

- Current season, selected months/weeks, or all-year union.
- Minimum occurrence probability/frequency.
- Maximum number of species, sorted by score.
- Common-only versus permissive/rare-species presets.
- Manual includes and excludes.
- One or two poses per species.

Before any paid work starts, the UI shows the source and meaning of the score, the ordered species list, total image count, capability warnings, and estimated upper cost. The user can edit the list and then confirm it.

If BirdNET-Go does not expose a stable API for range results, BirdFrame may invoke its documented `range print` command within the sidecar. The implementation must not scrape the BirdNET-Go web UI. An independently downloaded range model can be considered later, but is not required for BirdWeather-only version 1.

Artwork is also generated on demand when a confidently detected species is missing, so an incomplete regional list does not block display.

## 9. Artwork generation

### 9.1 Pipeline

The pipeline independently reimplements the useful parts of AvianVisitors while producing reusable bird cutouts and a local 16:9 composition:

1. Resolve scientific/common names to a stable BirdFrame species identifier.
2. Fetch a licensed anatomy reference and retain its source URL, author, and license metadata.
3. Build the versioned kachō-e style prompt with species, pose, diagnostic notes, negative constraints, and reference roles.
4. Call OpenRouter's dedicated image endpoint with a user-selected compatible image model.
5. Request transparent PNG directly when the selected endpoint supports it.
6. Otherwise generate against a consistent removable background and run a local background-removal step.
7. Crop, normalize, and validate the transparent asset.
8. Optionally run visual/anatomy verification through a user-selected vision model; do not silently incur this cost.
9. Store the source asset, normalized asset, prompt hash, model/provider, generation parameters, cost, and provenance.
10. Compose normalized bird assets locally into the exact TV output profile.

AvianVisitors' useful techniques to preserve are anatomy references, optional look-alike anti-references, style references, per-species diagnostic notes, paired poses, consistent removable backgrounds, post-generation verification, compact silhouette masks, and count-weighted packing. BirdFrame reimplements these ideas and does not copy AvianVisitors code or bundled artwork unless that is later reviewed and attributed separately.

### 9.2 Default art direction

The default preset is deliberately close to the AvianVisitors appearance:

- Edo-period Japanese kachō-e woodblock print.
- Very few marks: approximately two to four flat body color zones with sharp boundaries.
- Confident sumi-e ink linework with soft watercolor washes.
- Restrained earthy palette: burnt umber, ochre, indigo, vermillion, and muted greens.
- Crisp ink reserved primarily for eye, beak, feet, and essential diagnostic markings.
- Consistent warm cream aged-mulberry-paper ground during generation.
- No branch, twig, perch, foliage, scenery, border, caption, signature, or shadow.
- The entire bird remains inside the source frame with generous padding.
- Exactly two wings, two legs, one head, one beak, and one tail.
- Perched and flight poses match the species' proportions, markings, and diagnostic field references.

The source image is generated on the consistent cream ground when clean transparency is not supported, then locally cut out. The final collage restores a configurable warm-paper background so individual assets read as one coherent artwork.

Built-in appearance controls must preserve a valid prompt and layout:

- Paper tone and optional subtle paper texture.
- Palette preset and saturation.
- Sparse/standard/full collage density.
- Perched-versus-flight pose preference.
- Bird-area budget and safe margin.
- Optional labels and their typography.
- A versioned custom prompt addendum for advanced users.

The UI always offers “Reset to AvianVisitors-inspired default.” Completely replacing the prompt is an advanced action with a warning that it can break visual consistency and package compatibility.

### 9.3 OpenRouter integration

- API key is bring-your-own and encrypted at rest.
- Query OpenRouter's image-model catalog at runtime instead of hard-coding a stale model list.
- Show only models whose output modality includes images.
- Show price/capability data supplied by OpenRouter.
- Validate support for reference images, transparency, output format, resolution, and aspect ratio against the selected endpoint.
- Use the dedicated `POST /api/v1/images` endpoint.
- Limit concurrent requests, retry only retryable failures, and never retry a billable completed request automatically.
- Require explicit confirmation showing species count and an estimated upper cost before starting a regional batch.
- Support pause, resume, per-species retry, cancellation between requests, and export.

Bird assets may be generated square or portrait for better subject detail; the **delivered TV/API artwork is always composed at 16:9**. Both display modes normally reuse approved cutouts rather than generating a paid 16:9 image on every detection.

### 9.4 Quality checks

Automated checks:

- Decodable PNG/JPEG and expected color mode.
- Minimum resolution.
- Alpha/background-removal quality.
- Subject not clipped by image boundaries.
- Plausible non-empty bounding box.
- Anatomy audit, with particular attention to extra wings, detached feet, watermarks, stray perches, and incorrect look-alike markings.
- File-size and package limits.
- Exact 16:9 final dimensions.

Manual UI review:

- Approve/reject/regenerate each species.
- Compare alternate poses.
- Edit per-species generation notes.
- Preview the complete TV composition.

## 10. Pre-generated artwork packages

Packages are published as versioned GitHub Release assets, not built into the application image.

An HTTPS catalog JSON in a configured public GitHub repository lists packages. The catalog URL/repository is editable in Settings and defaults to the official BirdFrame catalog once published. Each entry contains:

- Package ID and semantic version.
- Display name and region definition.
- Style and layout compatibility.
- Species count and taxonomy version.
- Created date, generator/model metadata, and license.
- Download URL, byte size, and SHA-256 checksum.
- Minimum compatible BirdFrame version.

Each downloaded archive contains:

```text
manifest.json
LICENSES/
attribution.json
assets/species/<species-id>/<pose>.png
previews/
```

Install behavior:

- Fetch catalog over HTTPS.
- Download to a temporary file with progress and a size limit.
- Verify SHA-256 before extraction.
- Reject path traversal, symlinks, unexpected file types, incompatible schema, and excessive expanded size.
- Install atomically into the persistent art library.
- Keep the previous package version until the new version validates.
- Permit removal only for package-owned files.

The UI also exports locally generated art in the same format so users can contribute packages without exposing API keys.

## 11. Samsung Frame integration

Use `samsungtvws` (`xchwarze/samsung-tv-ws-api`) from the Python backend.

### 11.1 Discovery and pairing

- Discover Samsung TVs through LAN discovery where available, then query `http://<ip>:8001/api/v2/`.
- Prefer devices that report Frame/Art Mode support.
- Always provide manual IP entry because multicast discovery is unreliable across Docker, VLANs, and some routers.
- Require the TV and BirdFrame host to be on the same subnet unless the user has deliberately configured a supported proxy/NAT arrangement.
- Persist the Samsung authorization token in the BirdFrame data volume.
- Test Art Mode support before completing setup.

Linux host networking is recommended for the BirdFrame service because it improves LAN discovery and Wake-on-LAN behavior. The security documentation must explain that host networking exposes the configured web port directly on the LAN.

### 11.2 Upload lifecycle

For every update:

1. Render the exact output profile, normally 3840 × 2160 sRGB JPEG.
2. Connect with a bounded timeout.
3. Optionally wake the TV if permitted and outside quiet hours.
4. Upload with the configured matte, proposed default `none`.
5. Select the returned content ID and confirm it became current.
6. Record the content ID as BirdFrame-owned.
7. Delete the previous BirdFrame-owned upload only after the new image succeeds.

BirdFrame never deletes content it did not upload and track. Failed uploads are retried with backoff. Coalescing ensures that a burst of detections produces only the newest composition.

### 11.3 Known compatibility risk

Art Mode is an unofficial/private TV interface whose behavior has changed with Samsung firmware and model years. The app must:

- Show the exact failing operation and TV-reported information.
- Provide a connection diagnostic export.
- Allow upload/select/delete operations to be tested separately.
- Document same-subnet and TV permission settings.
- Maintain a tested-model compatibility table based on user reports.

No guarantee of support for every Frame model or firmware should be made.

## 12. Current-image API

BirdFrame exposes the exact image bytes used for the most recent successful or pending Samsung display update. This makes the compositor independent of any one display vendor.

### 12.1 Endpoints

- `GET /api/v1/display/current.jpg`
  - Returns the exact JPEG artifact selected for Samsung upload, without recomposition or transcoding.
  - Returns a built-in 16:9 waiting/setup image until the first composition exists.
  - Sends `Content-Type: image/jpeg`, `ETag`, `Last-Modified`, dimensions, composition ID, and cache revalidation headers.
  - Supports `HEAD` and conditional requests using `If-None-Match` and `If-Modified-Since`.
- `GET /api/v1/display/current.json`
  - Returns composition ID, revision, creation time, display mode, dimensions, image URL, ETag, and represented species/detection summary.
- `GET /api/v1/display/events`
  - Optional SSE stream announcing a new composition revision so capable displays can refresh immediately without aggressive polling.

The image endpoint always remains at a stable URL. Clients should use the ETag or metadata revision rather than cache-busting query strings.

### 12.2 Access policy

Read-only LAN access to the image is enabled by default so smart displays and dashboard applications can consume it easily. Settings allow the owner to:

- Disable the API.
- Require a long read-only bearer/query token for clients that cannot send normal authorization headers.
- Choose whether JSON metadata includes exact timestamps and confidence.
- Restrict access to configured private subnets.

API credentials are distinct from OpenRouter, BirdWeather, Samsung, and administrator credentials. The API never exposes those secrets, microphone audio, or internal file paths.

### 12.3 Output consistency

Composition is an immutable stored artifact. The database revision, web preview, current-image API, and Samsung upload job all reference the same file and SHA-256 digest. A later display failure does not cause the API and TV renderer to diverge; status records which revision the TV last confirmed.

## 13. Proposed implementation

### 13.1 Services

```text
Browser
  |
  v
BirdFrame web/application service
  |-- SQLite + encrypted secrets
  |-- job runner
  |-- 16:9 compositor
  |-- current-image HTTP API
  |-- Samsung Art Mode client
  |-- OpenRouter client
  |-- BirdWeather polling adapter
  |
  +---- BirdNET-Go SSE adapter ----> BirdNET-Go service ----> microphone
  |
  +---- LAN -----------------------> Samsung Frame TV
```

Recommended stack:

- Python 3.12.
- FastAPI backend with async I/O.
- SQLAlchemy/Alembic and SQLite in WAL mode.
- `samsungtvws` for TV control.
- Pillow, with an optional faster image backend only if needed.
- React + TypeScript + Vite frontend, compiled into the Python image.
- A database-backed in-process job queue for the first release. Jobs resume safely after restart.
- Pytest and Playwright for tests.

An in-process queue is sufficient because there is one hobby installation and one application replica. A separate Redis/Celery service would add operational weight without a first-release benefit.

### 13.2 Persistent storage

One mounted `/data` volume contains:

```text
/data/birdframe.db
/data/secret.key
/data/samsung-token
/data/art/
/data/packages/
/data/generated/
/data/previews/
/data/logs/
```

Microphone clips and BirdNET-Go's database remain in BirdNET-Go's own volume.

### 13.3 Internal modules

- `sources/birdnet_go`: SSE client and health checks.
- `sources/birdweather`: authenticated polling and cursor state.
- `detections`: canonical events, filtering, deduplication, and retention.
- `species`: taxonomy/name resolution and region lists.
- `art/generation`: OpenRouter model discovery and generation jobs.
- `art/packages`: catalog, validation, install, export.
- `art/compositor`: silhouette-aware deterministic 16:9 collage and latest-visitor layouts.
- `tv/samsung`: discovery, pairing, upload lifecycle, and diagnostics.
- `display`: immutable composition revisions and the current-image API.
- `settings`: validated configuration and encrypted secrets.
- `api`: browser API and server-sent status/job updates.

## 14. Docker and installation

The deliverable is one BirdFrame application image and an optional upstream BirdNET-Go image, orchestrated by one `docker-compose.yml`:

- **BirdWeather mode:** only the BirdFrame container is required.
- **Local microphone mode:** enable the `local-audio` Compose profile, which starts BirdNET-Go as the second container.

BirdFrame does not receive access to the Docker socket. If the user selects Local microphone while the sidecar is absent, the setup UI explains the requirement and shows the exact Compose command to enable it. Switching back to BirdWeather permits the BirdNET-Go profile to be stopped.

Targets:

- Linux ARM64 (Raspberry Pi 4/5 or similar).
- Linux AMD64 (mini PC, NAS, or home server).

Compose responsibilities:

- Pin released image versions; do not use `latest` for stable installs.
- Keep BirdNET-Go behind an opt-in `local-audio` profile.
- Map `/dev/snd` into BirdNET-Go only for local-microphone mode.
- Mount separate persistent volumes.
- Configure timezone and UID/GID.
- Use host networking where required for TV discovery/Wake-on-LAN and document the trade-off.
- Add health checks and restart policies.
- Expose only the BirdFrame web UI by default; BirdNET-Go's UI can be optionally exposed to the LAN for advanced administration.

Installation should be:

1. Install Docker Engine and Compose on supported Linux.
2. Download the release's Compose and example environment files.
3. Run `docker compose up -d` for BirdWeather mode, or `docker compose --profile local-audio up -d` for microphone mode.
4. Open `http://<host>:<port>`.
5. Complete the wizard.

## 15. Security and privacy

- Bind to the LAN by default and warn against direct internet exposure.
- Provide optional local authentication if remote LAN users are a concern.
- Generate a random installation secret on first start.
- Encrypt OpenRouter, BirdWeather, eBird, and current-image API tokens at rest with that installation secret.
- Redact tokens, Samsung pairing data, coordinates, and signed URLs from logs and support bundles.
- Apply SSRF protection to user-entered endpoints: BirdNET-Go may be a configured private address, but arbitrary schemes and public redirects are rejected.
- Enforce archive download size, extraction size, checksums, safe paths, and file allowlists.
- Never send microphone audio or BirdWeather soundscapes to OpenRouter.
- Show external data flows before enabling them.
- Use CSRF protection and secure cookie settings for state-changing browser actions.
- Rate-limit pairing, connection tests, generation, and package operations.
- Give the current-image API separate read-only access controls and never accept state-changing operations through it.

## 16. Documentation and quality bar

Documentation:

- `README.md`: what it does, screenshots, quick start, hardware, and limitations.
- `docs/installation.md`: Raspberry Pi/Linux installation and upgrades.
- `docs/setup.md`: wizard choices and configuration.
- `docs/microphone.md`: device selection and audio troubleshooting.
- `docs/birdweather.md`: station setup, token, polling, and privacy.
- `docs/samsung-frame.md`: pairing, supported behavior, firmware caveats, and diagnostics.
- `docs/display-api.md`: embedding the current image in other TVs, dashboards, and applications.
- `docs/artwork.md`: OpenRouter costs, generation, review, packages, and attribution.
- `docs/troubleshooting.md`: health checks, logs, backups, and recovery.
- `docs/development.md`: local development, tests, release process, and architecture.
- `THIRD_PARTY_NOTICES.md`, project license, and model/art license notices.

Minimum verification:

- Unit tests for source normalization, deduplication, policies, package safety, layout, and secret redaction.
- Contract tests using recorded/synthetic BirdNET-Go SSE and BirdWeather responses.
- A fake Samsung Art Mode server for pairing/upload/select/delete failure cases.
- Golden-image tests asserting exact output dimensions and stable deterministic layouts.
- API tests asserting that the served image digest is byte-for-byte identical to the Samsung upload artifact.
- Browser tests for first-run setup and key failure/retry paths.
- Multi-architecture container build in CI.
- Manual hardware acceptance test on at least one Frame TV before calling a release stable.

## 17. Resolved decisions and implementation defaults

- Both Collage and Latest visitor ship in version 1; Collage is the default.
- The deployment target is an always-on computer. Released containers target 64-bit Linux AMD64 and ARM64.
- Two containers are acceptable for microphone mode. BirdWeather mode requires only BirdFrame.
- The project is non-commercial.
- BirdFrame is inspired by and independently reimplements the AvianVisitors image and collage techniques.
- “Birdwatch model” means BirdNET. Its default model comes from the upstream BirdNET-Go distribution rather than BirdFrame.
- Exactly one detection source is active at a time.
- Wake-on-LAN is supported and configurable. It is an explicit setup choice; quiet hours and upload cadence are configurable.
- Regional pre-generation exposes probability/frequency threshold, maximum species, season, manual list editing, and cost review.
- The visual default closely follows AvianVisitors' kachō-e artwork. Appearance options are constrained presets with an advanced prompt addendum.
- The TV image is art-only by default. Interactive species information remains in the web UI, with labels available as an option.
- The package catalog/repository is configurable in Settings.
- The exact current display image is available through a generic read-only HTTP API.

One deployment fact still needs confirmation during installation rather than product design: local microphone and automatic TV discovery are supported as production paths on Linux. A BirdWeather-only installation may run elsewhere if container networking is sufficient, but Docker Desktop is not a guaranteed hardware-control target.

## 18. Acceptance criteria for version 1

- A fresh supported Linux machine can start BirdFrame alone for BirdWeather, or BirdFrame plus BirdNET-Go through the `local-audio` Compose profile.
- The setup wizard can configure either a USB microphone or a BirdWeather token.
- A synthetic or real qualifying detection appears in the BirdFrame history exactly once.
- The user can discover or manually configure a Frame TV, pair it, and pass an upload test.
- The user can install a checksum-verified regional package from the configured GitHub catalog.
- The user can select an occurrence source, probability/frequency threshold, season, and maximum species; review the exact ranked list and cost before generation.
- The user can configure OpenRouter, select a currently compatible image model, generate one species asset, approve it, and include it in a composition.
- Collage mode uses two-pose transparent assets, mask-aware collision, normalized count-weighted sizing, horizontal center-out packing, and safe-viewport repacking.
- Both Collage and Latest visitor produce an exact 16:9 immutable composition.
- Every uploaded image has the exact detected TV output size and 16:9 aspect ratio.
- `GET /api/v1/display/current.jpg` serves bytes with the same digest as the composition selected for Samsung upload.
- Detection bursts are coalesced and respect quiet hours and upload limits.
- BirdFrame deletes only content IDs that it previously uploaded and recorded.
- Restarting/upgrading containers preserves settings, secrets, artwork, detection cursor, jobs, and Samsung pairing.
- No API key, station token, exact coordinate, or Samsung token appears in normal logs or a support bundle.
- The documentation covers installation, setup, upgrades, backup, and the major known Samsung compatibility limitations.

## 19. Research basis

- [BirdNET-Go repository and feature overview](https://github.com/tphakala/birdnet-go)
- [BirdNET-Go documentation](https://github.com/tphakala/birdnet-go/wiki/)
- [BirdNET-Go Docker Compose guide](https://github.com/tphakala/birdnet-go/wiki/docker_compose_guide.md)
- [BirdNET Analyzer repository and model licensing](https://github.com/birdnet-team/BirdNET-Analyzer)
- [BirdWeather REST API](https://app.birdweather.com/api/v1)
- [BirdWeather GraphQL API](https://app.birdweather.com/api/index.html)
- [AvianVisitors repository](https://github.com/Twarner491/AvianVisitors)
- [AvianVisitors illustration pipeline](https://github.com/Twarner491/AvianVisitors/blob/avian-visitors/avian/scripts/README.md)
- [AvianVisitors project explanation: illustrations, collage, and real-time behavior](https://theodore.net/projects/AvianVisitors/#illustrations-collage)
- [Samsung TV WebSocket API library](https://github.com/xchwarze/samsung-tv-ws-api)
- [OpenRouter image generation API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
- [Samsung Art Mode user documentation](https://www.samsung.com/us/support/answer/ANS10005224/)
