# Installation

BirdFrame supports 64-bit Linux on a small PC, NAS, or Raspberry Pi 4/5. Samsung LAN discovery require native Linux networking.
Use a wired connection where practical; the TV and host should normally be on
the same subnet.

## Quick install (published image)

The fastest way to run BirdFrame is the published multi-architecture image —
no source checkout or build needed. It runs on amd64 and arm64:

```sh
mkdir -p ~/birdframe/data
docker run -d --name birdframe --restart unless-stopped \
  -p 8765:8765 \
  -v ~/birdframe/data:/data \
  -e TZ=Europe/Oslo \
  ghcr.io/simenf/birdframe:latest
```

Open `http://HOST_IP:8765` and complete the setup wizard. The `-v` bind mount
keeps your database, secrets, artwork, and logs in `~/birdframe/data`, so they
survive image updates. To update, pull the new image and recreate the
container:

```sh
docker pull ghcr.io/simenf/birdframe:latest
docker rm -f birdframe
docker run -d --name birdframe --restart unless-stopped \
  -p 8765:8765 \
  -v ~/birdframe/data:/data \
  -e TZ=Europe/Oslo \
  ghcr.io/simenf/birdframe:latest
```

For reliable Samsung TV discovery and Wake-on-LAN on Linux, prefer the Docker
Compose example at the bottom of this page, which uses host networking.

## Prerequisites

Install Docker Engine and the Docker Compose plugin from your distribution or
Docker's official instructions. Confirm that your normal account can run these:

```sh
docker version
docker compose version
```

Create the host directories before starting:

```sh
mkdir -p data 
docker compose up -d
docker compose ps
```

Open `http://HOST_IP:8765`. On a firewall-enabled host, allow the configured
`BIRDFRAME_PORT` only from trusted LAN ranges. Do not publish the UI directly
to the internet.

The Compose configuration uses `network_mode: host` on Linux so multicast TV
discovery and Wake-on-LAN work reliably. This means `BIRDFRAME_PORT` is a host
port, service names do not provide Compose DNS, and the application reaches a
local BirdNET-Go sidecar at `http://127.0.0.1:8765`.

## Detection modes

### BirdWeather

The default command starts one container:

```sh
docker compose up -d
```

Choose public station mode in the wizard to use public detections without a
token. A token is only needed for a private station or token-scoped requests;
no microphone device or BirdNET-Go container is needed in either case.

## Artwork and localization

The image-pack directory is optional. Put licensed packs under
`assets/packs/<pack-id>/` when building from source, or install them from the
Artwork settings page. The repository does not ship third-party image packs.
For the bundled Norwegian name database and its refresh procedure, see
[localization.md](localization.md).

## Upgrading

1. Back up `data/` and, for microphone installations, `birdnet-go-data/`.
2. Read the release notes and update the explicitly pinned image tags in `.env`.
3. Pull and recreate containers:

   ```sh
   docker compose pull
   docker compose --profile local-audio up -d
   ```

4. Confirm `docker compose ps` is healthy and inspect the dashboard.

Never run `docker compose down -v` for an upgrade: the `-v` flag removes named
volumes. This project uses bind mounts, but avoiding it keeps the intent clear.

## Example Docker Compose file

Save this as `docker-compose.yml` and run `docker compose up -d`:

```yaml
services:
  birdframe:
    image: ghcr.io/simenf/birdframe:latest
    container_name: birdframe
    restart: unless-stopped
    network_mode: host
    environment:
      TZ: Europe/Oslo
      BIRDFRAME_PORT: 8765
      BIRDFRAME_DATA_DIR: /data
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```

Notes:

- `network_mode: host` makes multicast TV discovery and Wake-on-LAN reliable.
  With host networking the app listens on port 8765 directly, so open
  `http://HOST_IP:8765` — no port mapping is needed.
- On Docker Desktop or macOS, replace host networking with a bridge and a port
  mapping: set `ports: ["8765:8765"]` and drop `network_mode`.
- `./data` is a bind mount. Back it up regularly and never remove it with
  `docker compose down -v`.

## Backup and restore

Stop services before a consistent filesystem backup:

```sh
docker compose down
tar -czf birdframe-backup-$(date +%F).tgz data birdnet-go-data
```

To restore, stop the service, replace the corresponding directories, preserve
their ownership, then start it again. Keep `data/secret.key` together with
`data/birdframe.db`; replacing either one independently can make saved secrets
unreadable.
