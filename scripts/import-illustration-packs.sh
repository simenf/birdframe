#!/usr/bin/env sh
set -eu

# Convert downloaded AvianVisitors repositories into small, directly usable
# BirdFrame source packs. It intentionally copies only artwork and the upstream
# dimensions/masks — never app code, model files, or Git metadata.
SOURCE_ROOT=${1:?Usage: scripts/import-illustration-packs.sh /path/to/downloaded/packs [destination]}
DESTINATION=${2:-assets/packs}

mkdir -p "$DESTINATION"
for source in "$SOURCE_ROOT"/*; do
  [ -d "$source" ] || continue
  pack=$(basename "$source")
  target="$DESTINATION/$pack"
  mkdir -p "$target"
  for treatment in illustrations sketches; do
    for candidate in "$source/$treatment" "$source/assets/$treatment" "$source/avian/assets/$treatment"; do
      if [ -d "$candidate" ]; then
        mkdir -p "$target/$treatment"
        cp -R "$candidate"/. "$target/$treatment/"
        break
      fi
    done
  done
  for metadata in dims.json masks.json; do
    for candidate in "$source/$metadata" "$source/assets/$metadata" "$source/avian/frontend/$metadata"; do
      if [ -f "$candidate" ]; then
        cp "$candidate" "$target/$metadata"
        break
      fi
    done
  done
done
