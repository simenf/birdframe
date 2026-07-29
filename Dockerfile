# syntax=docker/dockerfile:1
# Build context is the repository root. The backend exposes `birdframe.main:app`
# from backend/birdframe; its React UI is compiled from frontend/.
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package*.json ./
# npm 10 in the Node 22 image correctly resolves optional native Rollup
# packages across Linux architectures; `npm ci` rejects the cross-platform
# lockfile generated on macOS before it gets that chance.
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BIRDFRAME_DATA_DIR=/data \
    BIRDFRAME_PORT=8765
WORKDIR /app

# libjpeg/zlib are needed by Pillow; tini forwards shutdown signals cleanly.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libjpeg62-turbo zlib1g tini gosu \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ ./backend/
COPY --from=frontend-build /src/frontend/dist ./frontend-dist/
RUN pip install --no-cache-dir ./backend \
    && useradd --system --uid 10001 --create-home birdframe \
    && mkdir -p /data \
    && chown -R birdframe:birdframe /data
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/birdframe-entrypoint

EXPOSE 8765
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/birdframe-entrypoint"]
CMD ["sh", "-c", "uvicorn birdframe.main:app --host 0.0.0.0 --port ${BIRDFRAME_PORT:-8765}"]
