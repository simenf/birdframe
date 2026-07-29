# Source illustration packs

Place compact, usable BirdFrame packs here. The Docker build seeds them into
`/data/art/packages` on first start without overwriting a mapped data volume.

Use `scripts/import-illustration-packs.sh /path/to/downloaded/packs` to turn
the downloaded AvianVisitors repositories into clean packs containing only
`illustrations`, `sketches`, `dims.json`, and `masks.json`. The source images
are deliberately ignored by Git: they are large third-party artwork assets and
should be obtained from their upstream repositories or a properly licensed
release archive. Only this README and the ignore rule are tracked in a clean
checkout.

To make a distributable ZIP while keeping the original AvianVisitors layout:

```sh
python scripts/create-asset-pack.py assets/packs/avianvisitors-western-us \
  dist/avianvisitors-western-us.zip
```

Each pack is selectable in Settings. Choose **Illustrations** for the colour
plates or **Sketches** for the pencil studies.
