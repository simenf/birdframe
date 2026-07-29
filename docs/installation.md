# Installation

BirdFrame supports 64-bit Linux on a small PC, NAS, or Raspberry Pi 4/5. Local
microphone capture and Samsung LAN discovery require native Linux networking.
Use a wired connection where practical; the TV and host should normally be on
the same subnet.

## Prerequisites

Install Docker Engine and the Docker Compose plugin from your distribution or
Docker's official instructions. Confirm that your normal account can run these:

```sh
docker version
docker compose version
```

Clone a released source archive/repository, copy `.env.example` to `.env`, and
set at least `TZ`, `PUID`, `PGID`, and the versioned image tags. Find UID/GID
with `id -u` and `id -g`. Create the host directories before starting:

```sh
cp .env.example .env
mkdir -p data birdnet-go-data
docker compose up -d
docker compose ps
```

Open `http://HOST_IP:8765`. On a firewall-enabled host, allow the configured
`BIRDFRAME_PORT` only from trusted LAN ranges. Do not publish the UI directly
to the internet.

The Compose configuration uses `network_mode: host` on Linux so multicast TV
discovery and Wake-on-LAN work reliably. This means `BIRDFRAME_PORT` is a host
port, service names do not provide Compose DNS, and the application reaches a
local BirdNET-Go sidecar at `http://127.0.0.1:8080`.

## Detection modes

### BirdWeather

The default command starts one container:

```sh
docker compose up -d
```

Choose public station mode in the wizard to use public detections without a
token. A token is only needed for a private station or token-scoped requests;
no microphone device or BirdNET-Go container is needed in either case.

### Local microphone

Start the optional profile on a Linux host:

```sh
docker compose --profile local-audio up -d
```

This maps `/dev/snd` only into BirdNET-Go. Verify the device exists on the host
with `arecord -l` (install `alsa-utils` if needed), then use the linked
BirdNET-Go page to select/test it. Refer to [microphone.md](microphone.md).

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
