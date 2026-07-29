# BirdFrame

BirdFrame is a self-hosted, non-commercial bird visitor display for Samsung The
Frame TVs. It receives detections from either a local microphone via
[BirdNET-Go](https://github.com/tphakala/birdnet-go) or an existing
[BirdWeather](https://www.birdweather.com) station, builds an evolving 16:9
kachō-e-inspired collage, and sends the exact same JPEG to the TV and a stable
HTTP endpoint for other displays.

It is designed for an always-on 64-bit Linux computer. Collage mode is the
default; “latest visitor” mode reuses the same approved bird artwork.

> This is a hobby/non-commercial project. It does not include BirdNET model
> files or any generated artwork. Review [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md),
> the selected model terms, and every artwork package's attribution before use.

## Quick start

Requirements: 64-bit Linux (AMD64 or ARM64), Docker Engine with the Compose
plugin, a browser on the same LAN, and a Samsung TV only if you want direct TV
control. Docker Desktop is fine for trying BirdWeather mode, but is not a
supported local-microphone or LAN-discovery host.

```sh
git clone https://github.com/birdframe-project/birdframe.git
cd birdframe
cp .env.example .env
mkdir -p data birdnet-go-data
docker compose up -d
```

Open `http://HOSTNAME-OR-IP:8765` and complete the setup wizard. The default
starts only BirdFrame, for use with public BirdWeather data or prepared artwork.
A private BirdWeather token is optional.

For a USB/local microphone on Linux, start the optional upstream sidecar:

```sh
docker compose --profile local-audio up -d
```

The container receives `/dev/snd`; select and test its microphone in the
BirdNET-Go administration page linked from BirdFrame. See
[docs/installation.md](docs/installation.md) before deploying permanently.

Artwork packs are deliberately not redistributed by this repository. Import a
licensed pack into `assets/packs/<pack-id>/` (or install one from the UI) only
after checking its manifest and attribution; see [docs/artwork.md](docs/artwork.md).

## What is sent where

- Audio stays in BirdNET-Go on your host. BirdFrame does not send microphone
  audio to OpenRouter.
- Public BirdWeather mode reads public detections using a station ID (for
  example `2505`) and needs no credential. Private-station mode asks
  BirdWeather only for the detections authorized by your token.
- Artwork generation sends text prompts and only the references you explicitly
  select to your chosen OpenRouter model/provider.
- Samsung control and image upload occur over your local network.

## Persistent artwork and logs

Docker Compose bind-mounts `${BIRDFRAME_DATA_DIR:-./data}` to `/data` in the
container. Generated species PNGs, installed packages, rendered JPEGs, the
SQLite database, encrypted secrets, and the in-app activity log therefore
survive image rebuilds and container replacement. Back up the host `./data`
directory before moving an installation.

## Generic display API

The composition does not depend on the Samsung integration. Other devices can
display the exact JPEG selected for TV upload:

```text
GET /api/v1/display/current.jpg
GET /api/v1/display/current.json
GET /api/v1/display/events
```

Read [docs/display-api.md](docs/display-api.md) for caching, authentication,
and embedding examples.

## Operations

```sh
# Check service state and recent logs
docker compose ps
docker compose logs --tail=100 birdframe

# Upgrade after updating BIRDFRAME_VERSION in .env
docker compose pull
docker compose up -d

# Stop without removing persistent data
docker compose down
```

Back up the `data/` directory while the service is stopped. It contains the
database, encryption key, TV token, settings, artwork, and display artifacts.
Do not lose `data/secret.key`: encrypted tokens cannot be recovered without it.

## Documentation

- [Installation and upgrades](docs/installation.md)
- [Setup wizard](docs/setup.md)
- [Microphone and BirdNET-Go](docs/microphone.md)
- [BirdWeather](docs/birdweather.md)
- [Samsung Frame](docs/samsung-frame.md)
- [Display API](docs/display-api.md)
- [Artwork and packages](docs/artwork.md)
- [Localization and Norwegian names](docs/localization.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development](docs/development.md)

## Publishing and licensing

The repository is ready to build from a clean checkout, but a release
maintainer still needs to choose a GitHub owner, publish a container image, and
review each optional artwork/model license. Source code and original
documentation are CC BY-NC-SA 4.0; see [LICENSE](LICENSE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Local runtime state is ignored
by Git and must never be committed.
