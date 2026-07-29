# Development

BirdFrame has a Python/FastAPI backend in `backend/` and a React/TypeScript UI
in `frontend/`. The production Dockerfile builds the UI and copies it to
`/app/frontend-dist`, where the backend serves it.

## Local development

Use Python 3.12 and a current Node LTS release. A clean checkout does not need
the ignored runtime `data/` directory or third-party artwork packs to run the
unit tests.

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn birdframe.main:app --reload --port 8765
```

In a second terminal:

```sh
cd frontend
npm install
npm run dev
```

Set the frontend development proxy/API base URL according to its local README or
Vite configuration. Use synthetic BirdNET-Go SSE and BirdWeather fixtures in
tests; do not require live provider keys or a real TV.

Refresh the Norwegian name data only when the upstream workbook changes:

```sh
python scripts/import-norwegian-bird-names.py /path/to/AviList2025NNKFkomplett.xlsx
```

## Verification

```sh
cd backend && pytest
cd frontend && npm run test --if-present && npm run build
docker build -t birdframe:dev .
```

Required coverage includes input normalization/deduplication, display policy,
safe package extraction, secret redaction, deterministic collage golden images,
and the invariant that the current-image response digest equals the artifact
sent to the Samsung client. Contract-test both detection adapters and use a fake
Samsung Art Mode server for failure paths.

## Release checklist

1. Update version metadata, changelog/release notes, and pin image digests/tags.
2. Build/test AMD64 and ARM64 images in CI.
3. Produce dependency notices from locked dependencies and update
   `THIRD_PARTY_NOTICES.md`.
4. Test a clean BirdWeather install and an optional native-Linux microphone
   install.
5. Manually test discovery/manual-IP, pairing, upload, select, and owned-image
   deletion on at least one Frame model.
6. Publish the image and a package catalog only after checksums and artifact
   licenses are verified.

Never add provider tokens, Samsung pairing tokens, `data/`, model weights, or
generated artwork to git. Keep implementation changes independently inspired by
AvianVisitors; do not copy its code/assets without a separate license review.

GitHub Actions runs the backend test suite and frontend production build for
every push and pull request. Docker image publishing is intentionally not
automatic until a maintainer selects a registry and release policy.
