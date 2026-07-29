# Current display API

BirdFrame publishes one immutable composition revision at a stable LAN URL.
The JPEG bytes are the same artifact selected for Samsung upload; it is not a
preview, redirect, or re-render.

| Endpoint | Use |
| --- | --- |
| `GET` / `HEAD` `/api/v1/display/current.jpg` | Current 16:9 JPEG |
| `GET` `/api/v1/display/current.json` | Revision, dimensions, ETag, mode, and species summary |
| `GET` `/api/v1/display/events` | Optional server-sent events for revision changes |

Until the first composition exists, `current.jpg` returns a built-in 16:9 setup
image. The URL remains stable when compositions change.

## Caching

Use `ETag` (recommended) or `Last-Modified`; clients should send
`If-None-Match` or `If-Modified-Since` and respect a `304 Not Modified` response.
Do not append cache-busting timestamps. `current.json` includes the same
revision and image ETag for clients that prefer polling metadata first.

Example with curl:

```sh
curl -D headers.txt -o current.jpg http://BIRDFRAME_HOST:8765/api/v1/display/current.jpg
curl -H 'If-None-Match: "PASTE_ETAG_HERE"' -I http://BIRDFRAME_HOST:8765/api/v1/display/current.jpg
```

## Embedding

A basic dashboard can point an image element at the stable URL and refresh when
the ETag/revision changes. A device that accepts a URL can poll the JSON endpoint
every few minutes, download the JPEG only on a revision change, and preserve the
last valid image when BirdFrame is unavailable.

## Access control

LAN read access is enabled by default. In Settings, an owner can disable the
API, require its separate read-only token, hide detailed timestamps/confidence
from metadata, and restrict allowed private subnets. This token is not an
administrator login and must never be an OpenRouter, BirdWeather, or Samsung
credential. Use HTTPS/reverse-proxy authentication if exposing the service
beyond a trusted LAN; direct public exposure is unsupported.
