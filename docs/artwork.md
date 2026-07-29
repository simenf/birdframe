# Artwork, OpenRouter, and packages

BirdFrame generates reusable transparent bird assets, then composes them
locally into a 16:9 warm-paper artwork. It does not buy a new full-screen image
for each detection.

## Art direction and review

The default preset is inspired by Japanese kachō-e prints: sparse, restrained
color zones, sumi-e-like linework, a warm paper ground, no scenery or labels,
and paired perched/flight poses. It is independently implemented and does not
include AvianVisitors code or art.

Settings offer bounded choices for paper, palette, density, pose balance, safe
margin, labels, and a versioned advanced prompt addendum. Use **Reset to
AvianVisitors-inspired default** to return to the compatible baseline. Review
each generated asset before it can appear in a collage; reject/regenerate
misidentified anatomy, clipped birds, watermarks, detached feet, extra wings,
or unwanted perches.

## OpenRouter generation

Enter your own API key in the wizard. BirdFrame queries the current catalog and
shows compatible image models rather than relying on a fixed model list. Before
a batch begins it shows the species list, pose count, provider capability
warnings, and estimated upper cost. Confirm explicitly; jobs can pause, resume,
cancel between requests, and retry individual failures.

Your key is encrypted in the persistent data directory and never returned by the
web API. References and prompts may leave your host for the provider. Check the
selected model's usage, output, and commercial-use terms; BirdFrame itself is
licensed for non-commercial use.

## Pre-generated packages

Configure a public HTTPS GitHub catalog URL in Settings. A package catalog
entry specifies its version, region, style/layout compatibility, checksum,
download URL, and minimum BirdFrame version. Installation downloads to a
temporary location, verifies SHA-256 and archive safety, validates the manifest,
then atomically adds it to the art library.

The Settings page also supports two direct installation paths: choose a local
`.zip` file, or paste a direct HTTPS ZIP URL. Both operations are queued as
jobs and appear in Activity log. Catalog entries can be loaded and installed
from the same page. Direct URLs do not provide a catalog checksum, so prefer a
catalog entry with a published SHA-256 when distributing packs publicly.

The source repository does not commit third-party PNG artwork. When building
from source, `scripts/import-illustration-packs.sh` can copy a licensed upstream
pack into `assets/packs/`; those files remain ignored by Git and are seeded into
the persistent art directory on first container start.

To create a shareable ZIP from one of those downloaded packs, run
`python scripts/create-asset-pack.py assets/packs/<pack-id> output.zip`. The
script preserves the AvianVisitors-compatible directories and adds a small
`manifest.json`; include the upstream license and attribution files before
sharing.

Packages contain `manifest.json`, `LICENSES/`, `attribution.json`, assets, and
previews. BirdFrame rejects unsafe paths, symlinks, unknown file types, overly
large archives, and incompatible schemas. Package licenses and attribution
apply to their contents; do not assume a package is licensed like BirdFrame.

Locally generated assets can be exported in the same package format for sharing
only when you have the necessary rights to the source references and outputs.
