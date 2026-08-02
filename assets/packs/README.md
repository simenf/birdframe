# Source illustration packs

Place compact, usable BirdFrame packs here. They are no longer baked into the
Docker image; use them as the source for the shareable avianassets catalog, or
install packs from a catalog URL at runtime (Settings → Asset Packs).

Use `scripts/import-illustration-packs.sh /path/to/downloaded/packs` to turn
the downloaded AvianVisitors repositories into clean packs containing only
`illustrations`, `sketches`, `dims.json`, and `masks.json`. The original
`cutouts/` directory is a separate bird-detail/fallback asset and is not
needed by the BirdFrame collage. The source images
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
