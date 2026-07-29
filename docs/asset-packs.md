# Asset-pack authoring guide

BirdFrame asset packs are portable ZIP archives containing transparent bird
artwork and the metadata used by the AvianVisitors-style compositor. The goal
is that a pack made for BirdFrame can be reviewed and shared with the original
AvianVisitors community without changing the artwork layout.

## Source directory layout

Start with a directory named after the pack:

```text
my-region/
├── illustrations/
│   ├── turdus-merula.png
│   └── turdus-merula-2.png
├── sketches/                 # optional pencil versions
│   ├── turdus-merula.png
│   └── turdus-merula-2.png
├── dims.json                 # optional upstream placement dimensions
├── masks.json                # optional upstream silhouette masks
├── attribution.json          # recommended
└── LICENSES/                 # required when redistributing third-party art
    └── source-license.txt
```

Use lowercase scientific-name slugs for filenames (`genus-species.png`). A
second pose conventionally uses `-2` and the compositor can use either pose.
Keep PNGs in RGBA format with transparent backgrounds. Do not flatten a bird
onto a paper background: BirdFrame supplies the 16:9 paper and performs the
mask-aware placement.

`dims.json` and `masks.json` are optional for generated packs, but retaining
them from an AvianVisitors source pack gives the closest original layout.

## Build a ZIP

After obtaining or preparing a licensed source directory:

```sh
python scripts/create-asset-pack.py \
  assets/packs/my-region \
  dist/my-region.zip \
  --id my-region
```

The script copies only the artwork, compatibility tables, attribution,
license directories, and a generated `manifest.json`. It does not include Git
metadata, application code, model files, or unrelated repository files.

Inspect the result before sharing:

```sh
unzip -l dist/my-region.zip
sha256sum dist/my-region.zip
```

## Manifest

The generated manifest follows the AvianVisitors-compatible format:

```json
{
  "package_id": "my-region",
  "format": "avianvisitors-v1",
  "illustrations": "illustrations",
  "sketches": "sketches",
  "dims": "dims.json",
  "masks": "masks.json"
}
```

Paths are relative to the archive root. A pack may contain only illustrations
or only sketches. The installer also accepts an unmodified AvianVisitors ZIP
without a manifest and generates compatible metadata when it finds an
`illustrations/` directory.

## Attribution and licensing

Every redistributed pack should include:

1. `LICENSES/` containing the applicable license text.
2. `attribution.json` identifying the artist, source project, and URLs.
3. A README describing modifications, if any.

Example attribution:

```json
{
  "name": "My regional bird plates",
  "source": "https://example.org/original-project",
  "artists": ["Artist Name"],
  "license": "CC BY 4.0",
  "modifications": "Cropped to transparent PNGs; filenames preserved."
}
```

Do not bundle BirdNET model files, generated OpenRouter output without rights,
or images whose license does not permit redistribution. The BirdFrame source
license does not automatically apply to pack contents.

## Publishing a catalog

A catalog is a public HTTPS JSON file. Each entry needs a safe ID, a direct
HTTPS ZIP URL, and the archive SHA-256:

```json
{
  "packages": [
    {
      "id": "my-region",
      "version": "1.0.0",
      "download_url": "https://downloads.example.org/my-region.zip",
      "sha256": "<64 lowercase hexadecimal characters>",
      "region": "Norway",
      "style": "avianvisitors-v1"
    }
  ]
}
```

Host the catalog and ZIP over HTTPS. BirdFrame verifies the catalog checksum
before unpacking, rejects unsafe archive paths and unsupported file types, and
installs atomically into persistent `/data/art/packages/<id>`.

## Installing and testing

In Settings, use **Asset packs** to:

- upload a local ZIP;
- install a direct HTTPS ZIP URL;
- save and load a catalog; and
- install a catalog entry.

Installation is asynchronous. Follow the job in **Activity log**, then select
the pack and treatment under **Collage style**. For a source build, placing a
pack under `assets/packs/` causes Docker to seed it into `/data/art/packages`
on first startup; mapped data is never overwritten on later restarts.

Before publishing, test both treatments, a species with two poses, a species
with no matching asset, and a full-screen 16:9 composition. Run the automated
checks as well:

```sh
.venv/bin/python -m pytest -q backend/tests
npm run build --prefix frontend
```
