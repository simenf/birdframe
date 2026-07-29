# Source illustration packs

Place compact, usable BirdFrame packs here. The Docker build seeds them into
`/data/art/packages` on first start without overwriting a mapped data volume.

Use `scripts/import-illustration-packs.sh /path/to/downloaded/packs` to turn
the downloaded AvianVisitors repositories into clean packs containing only
`illustrations`, `sketches`, `dims.json`, and `masks.json`. The source images
are deliberately ignored by Git: they are large third-party artwork assets and
should be obtained from their upstream repositories or a release archive.

Each pack is selectable in Settings. Choose **Illustrations** for the colour
plates or **Sketches** for the pencil studies.
