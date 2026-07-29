#!/usr/bin/env python3
"""Create a shareable AvianVisitors-compatible BirdFrame ZIP pack.

The source directory is copied without changing the upstream asset layout.
Only the artwork directories, compatibility tables, attribution, and a small
BirdFrame manifest are included.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from pathlib import Path
from shutil import copy2, copytree

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
INCLUDED_FILES = ("dims.json", "masks.json", "attribution.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Downloaded AvianVisitors pack directory")
    parser.add_argument("output", type=Path, help="Output .zip path")
    parser.add_argument("--id", dest="package_id", help="Safe package id (defaults to source name)")
    args = parser.parse_args()
    package_id = (args.package_id or args.source.name).lower()
    if not SAFE_ID.fullmatch(package_id):
        parser.error("package id must contain only lowercase letters, numbers, '.', '_' or '-'")
    if not args.source.is_dir():
        parser.error(f"source directory does not exist: {args.source}")
    treatments = [name for name in ("illustrations", "sketches") if (args.source / name).is_dir()]
    if not treatments:
        parser.error("source must contain illustrations/ or sketches/")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="birdframe-pack-") as temporary:
        staging = Path(temporary) / package_id
        staging.mkdir()
        for treatment in treatments:
            copytree(args.source / treatment, staging / treatment)
        for filename in INCLUDED_FILES:
            source = args.source / filename
            if source.is_file():
                copy2(source, staging / filename)
        for directory in ("LICENSES", "licenses"):
            source = args.source / directory
            if source.is_dir():
                copytree(source, staging / directory)
        manifest = {
            "package_id": package_id,
            "format": "avianvisitors-v1",
            "illustrations": "illustrations" if "illustrations" in treatments else None,
            "sketches": "sketches" if "sketches" in treatments else None,
            "dims": "dims.json" if (staging / "dims.json").exists() else None,
            "masks": "masks.json" if (staging / "masks.json").exists() else None,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(staging))
    print(f"created {args.output} ({package_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
