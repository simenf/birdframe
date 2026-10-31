#!/usr/bin/env python3
"""Create a BirdFrame ZIP pack or AvianVisitors hosted-bundle upload ZIP.

BirdFrame mode preserves the source layout and includes compatibility tables
plus BirdFrame metadata. AvianVisitors mode emits its checksummed, per-image
manifest and a single selected treatment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
from shutil import copy2, copytree
from urllib.parse import urlsplit

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
AVIAN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
AVIAN_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_SPECIES = 5000
INCLUDED_FILES = ("dims.json", "masks.json", "attribution.json")
AVIAN_LICENSES = ("CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-SA-4.0", "LicenseRef-NoC-US")


def _avianvisitors_manifest(source: Path, treatment: str, args: argparse.Namespace) -> tuple[dict[str, object], list[Path]]:
    if not AVIAN_ID.fullmatch(args.package_id) or not AVIAN_VERSION.fullmatch(args.version):
        raise ValueError("AvianVisitors bundle id or version is invalid")
    required = (args.name, args.style_id, args.style_name, args.coverage_type, args.coverage_label, args.license, args.creator, args.source_url)
    if any(not value for value in required):
        raise ValueError("AvianVisitors export requires --name, --style-id, --style-name, --coverage-type, --coverage-label, --license, --creator, and --source-url")
    if args.license not in AVIAN_LICENSES:
        raise ValueError(f"license must be one of: {', '.join(AVIAN_LICENSES)}")
    if not args.source_url.startswith("https://"):
        raise ValueError("--source-url must use HTTPS")
    if not AVIAN_ID.fullmatch(args.style_id) or any(len(value) > maximum for value, maximum in ((args.name, 90), (args.description, 260), (args.style_name, 90), (args.coverage_label, 90), (args.creator, 100))):
        raise ValueError("bundle name, style id, coverage label, creator, or description is invalid or too long")
    try:
        parsed_source = urlsplit(args.source_url)
        parsed_source.port
    except ValueError as exc:
        raise ValueError("--source-url must be a valid HTTPS URL") from exc
    if parsed_source.scheme != "https" or not parsed_source.hostname or parsed_source.username or parsed_source.password or len(args.source_url) > 500:
        raise ValueError("--source-url must be a valid HTTPS URL")
    region_codes = sorted(set(args.region_code or []))
    if any(not re.fullmatch(r"[A-Z]{2}(?:-[A-Z0-9]{1,8}){0,3}", code) for code in region_codes):
        raise ValueError("region codes must use ISO-like codes such as US-CA or GB-ENG-DBY")
    if args.coverage_type == "region" and not region_codes:
        raise ValueError("--coverage-type region requires at least one --region-code")
    if args.coverage_type == "global" and region_codes:
        raise ValueError("global bundles must not include --region-code")

    root = source / treatment
    images = sorted(path for path in root.glob("*.png") if path.is_file())
    if not images:
        raise ValueError(f"source has no PNGs under {treatment}/")
    species: dict[str, list[tuple[int, Path]]] = {}
    for path in images:
        stem = path.stem
        match = re.fullmatch(r"(.+?)(?:-([2-9]|[12][0-9]|3[0-2]))?", stem)
        if not match:
            raise ValueError(f"unexpected illustration filename: {path.name}")
        slug = match.group(1)
        if not re.fullmatch(r"[a-z]+(?:-[a-z]+)+", slug):
            raise ValueError(f"expected lowercase scientific-name slug: {path.name}")
        parts = slug.split("-")
        if len(parts) > 4 or any(not 2 <= len(part) <= 40 for part in parts):
            raise ValueError(f"scientific-name slug is not supported by the AvianVisitors manifest: {path.name}")
        scientific_name = " ".join([parts[0].capitalize(), *parts[1:]])
        if re.fullmatch(r"[A-Z][A-Za-z-]{1,39}(?: [a-z][A-Za-z-]{1,39}){1,3}", scientific_name) is None:
            raise ValueError(f"scientific-name slug is not supported by the AvianVisitors manifest: {path.name}")
        pose_number = int(match.group(2) or "1")
        species.setdefault(slug, []).append((pose_number, path))

    uses_variants = args.license == "LicenseRef-NoC-US" or any(number > 2 for poses in species.values() for number, _ in poses)
    if len(species) > MAX_SPECIES:
        raise ValueError("AvianVisitors bundles may contain at most 5,000 species")
    rows: list[dict[str, object]] = []
    included_images: list[Path] = []
    total_bytes = 0
    for slug, poses in sorted(species.items()):
        scientific_name = " ".join([slug.split("-")[0].capitalize(), *slug.split("-")[1:]])
        pose_rows: list[dict[str, object]] = []
        seen_numbers: set[int] = set()
        for number, path in sorted(poses):
            if number in seen_numbers:
                raise ValueError(f"duplicate pose {number} for {slug}")
            seen_numbers.add(number)
            if uses_variants:
                pose_id = f"variant-{number}"
            else:
                pose_id = "perched" if number == 1 else "flight"
            relative = f"illustrations/{slug}{f'-{number}' if number > 1 else ''}.png"
            size = path.stat().st_size
            if not 67 <= size <= MAX_IMAGE_BYTES:
                raise ValueError(f"image size is outside the AvianVisitors limit: {path.name}")
            total_bytes += size
            if total_bytes > MAX_TOTAL_BYTES:
                raise ValueError("AvianVisitors bundle exceeds the 1 GB image limit")
            raw = path.read_bytes()
            pose_rows.append({"id": pose_id, "file": relative, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
            included_images.append(path)
        rows.append({"scientific_name": scientific_name, "poses": pose_rows})

    manifest: dict[str, object] = {
        "format": "avian-visitors-asset-pack",
        "format_version": 2 if uses_variants else 1,
        "id": args.package_id,
        "version": args.version,
        "name": args.name,
        "description": args.description or "",
        "style": {"id": args.style_id, "name": args.style_name},
        "coverage": {"type": args.coverage_type, "label": args.coverage_label, **({"region_codes": region_codes} if region_codes else {})},
        "species": rows,
        "license": {"spdx": args.license},
        "attribution": {"creator": args.creator, "source_url": args.source_url},
    }
    if args.license_file:
        license_path = Path(args.license_file)
        if license_path.is_absolute() or ".." in license_path.parts or not (source / license_path).is_file():
            raise ValueError("--license-file must name an existing file relative to the pack directory")
        manifest["license"] = {"spdx": args.license, "file": license_path.as_posix()}
    if uses_variants:
        manifest["format_version"] = 2
    return manifest, included_images


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Downloaded AvianVisitors pack directory")
    parser.add_argument("output", type=Path, help="Output .zip path")
    parser.add_argument("--id", dest="package_id", help="Safe package id (defaults to source name)")
    parser.add_argument("--format", choices=("birdframe", "avianvisitors"), default="birdframe", help="Keep the AvianAssets ZIP format, or create an AvianVisitors hosted-bundle upload ZIP")
    parser.add_argument("--version", default="1.0.0", help="Bundle version for --format avianvisitors")
    parser.add_argument("--name", help="Public bundle name for --format avianvisitors")
    parser.add_argument("--description", default="", help="Optional public description for --format avianvisitors")
    parser.add_argument("--style-id", help="AvianVisitors style id")
    parser.add_argument("--style-name", help="AvianVisitors style name")
    parser.add_argument("--coverage-type", choices=("region", "global", "selection"), help="Coverage kind for --format avianvisitors")
    parser.add_argument("--coverage-label", help="Coverage label for --format avianvisitors")
    parser.add_argument("--region-code", action="append", help="Coverage code; repeat for multiple regions")
    parser.add_argument("--license", choices=AVIAN_LICENSES, help="SPDX license id from AvianVisitors' supported set")
    parser.add_argument("--license-file", help="Optional license text path relative to the source pack")
    parser.add_argument("--creator", help="Creator attribution for --format avianvisitors")
    parser.add_argument("--source-url", help="HTTPS source or attribution URL for --format avianvisitors")
    parser.add_argument("--treatment", choices=("illustrations", "sketches"), default="illustrations", help="Single artwork treatment to export as a hosted bundle")
    args = parser.parse_args()
    package_id = (args.package_id or args.source.name).lower()
    if not SAFE_ID.fullmatch(package_id):
        parser.error("package id must contain only lowercase letters, numbers, '.', '_' or '-'")
    if not args.source.is_dir():
        parser.error(f"source directory does not exist: {args.source}")
    args.package_id = package_id
    treatments = [name for name in ("illustrations", "sketches") if (args.source / name).is_dir()]
    if not treatments:
        parser.error("source must contain illustrations/ or sketches/")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="birdframe-pack-") as temporary:
        staging = Path(temporary) / package_id
        staging.mkdir()
        if args.format == "avianvisitors":
            try:
                manifest, images = _avianvisitors_manifest(args.source, args.treatment, args)
            except ValueError as exc:
                parser.error(str(exc))
            image_dir = staging / "illustrations"
            image_dir.mkdir()
            for source in images:
                copy2(source, image_dir / source.name)
            for directory in ("LICENSES", "licenses"):
                license_dir = args.source / directory
                if license_dir.is_dir():
                    copytree(license_dir, staging / directory)
            if args.license_file:
                license_source = args.source / args.license_file
                license_target = staging / args.license_file
                license_target.parent.mkdir(parents=True, exist_ok=True)
                copy2(license_source, license_target)
            attribution = args.source / "attribution.json"
            if attribution.is_file():
                copy2(attribution, staging / attribution.name)
        else:
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
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(staging))
    print(f"created {args.output} ({package_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
