"""Read and install AvianVisitors' hosted illustration bundles."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from PIL import Image

from .packages import PackageError, SAFE_ID

COMMUNITY_CATALOG_URL = "https://avianvisitors.com/api/bundles/catalog/community-v1.json"
OFFICIAL_CATALOG_URL = "https://raw.githubusercontent.com/Twarner491/AvianVisitors/avian-visitors/frame/vendor/catalog-v1.json"
OBJECT_BASE_URL = "https://avianvisitors.com/api/bundles/objects/"
MANIFEST_BASE_URL = "https://avianvisitors.com/api/bundles/manifests/"
COMMUNITY_FORMAT = "avian-visitors-bundle-catalog"
OFFICIAL_FORMAT = "avian-visitors-frame-bundle-catalog"
MANIFEST_FORMAT = "avian-visitors-asset-pack"
MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_BYTES = 1024 * 1024 * 1024
MAX_SPECIES = 5000
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
SCIENTIFIC_RE = re.compile(r"^[A-Z][A-Za-z-]{1,39}(?: [a-z][A-Za-z-]{1,39}){1,3}$")
REGION_RE = re.compile(r"^[A-Z]{2}(?:-[A-Z0-9]{1,8}){0,3}$")
LICENSES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-SA-4.0", "LicenseRef-NoC-US"}
POSES_V1 = {"perched", "flight"}
POSES_V2 = {f"variant-{number}" for number in range(1, 33)}


def _invalid(label: str) -> PackageError:
    return PackageError(f"AvianVisitors {label} is invalid")


def _exact_keys(value: Any, required: set[str], optional: set[str], label: str) -> None:
    if not isinstance(value, dict) or required - set(value) or set(value) - required - optional:
        raise _invalid(label)


def _text(value: Any, label: str, maximum: int, *, optional: bool = False) -> str:
    if optional and (value is None or value == ""):
        return ""
    if not isinstance(value, str):
        raise _invalid(label)
    clean = " ".join(value.split())
    if not clean or len(clean) > maximum or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value) or "<" in value or ">" in value:
        raise _invalid(label)
    return clean


def _checked_hash(value: Any) -> str:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise _invalid("SHA-256")
    return value


def _checked_ref(value: Any) -> dict[str, Any]:
    _exact_keys(value, {"url", "sha256", "bytes"}, set(), "manifest reference")
    digest = _checked_hash(value["sha256"])
    size = value["bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or not 2 <= size <= MAX_MANIFEST_BYTES:
        raise _invalid("manifest reference")
    expected_url = MANIFEST_BASE_URL + digest + ".json"
    if value["url"] != expected_url:
        raise _invalid("manifest URL")
    return {"url": expected_url, "sha256": digest, "bytes": size}


def _checked_preview(value: Any) -> dict[str, Any]:
    _exact_keys(value, {"scientific_name", "common_name", "pose", "sha256", "bytes"}, set(), "catalog preview")
    scientific = _text(value.get("scientific_name"), "preview species", 163)
    size = value.get("bytes")
    if SCIENTIFIC_RE.fullmatch(scientific) is None or not isinstance(value.get("pose"), str) or value["pose"] not in POSES_V1 | POSES_V2 or isinstance(size, bool) or not isinstance(size, int) or not 67 <= size <= MAX_IMAGE_BYTES:
        raise _invalid("catalog preview")
    return {
        "scientific_name": scientific,
        "common_name": _text(value.get("common_name"), "preview common name", 100, optional=True),
        "pose": value["pose"],
        "sha256": _checked_hash(value["sha256"]),
        "bytes": size,
    }


def _checked_common_row(source: Any, *, community: bool) -> dict[str, Any]:
    if community:
        required = {"id", "version", "name", "description", "creator", "repository_url", "coverage", "style", "species_count", "species", "review", "availability", "manifest", "archive_bytes", "previews", "license"}
        _exact_keys(source, required, set(), "community catalog entry")
    else:
        _exact_keys(source, {"id", "version", "name", "availability", "manifest"}, set(), "official catalog entry")
    package_id = source.get("id")
    version = source.get("version")
    name = _text(source.get("name"), "bundle name", 90)
    if not isinstance(package_id, str) or SAFE_ID.fullmatch(package_id) is None or len(package_id) > 80:
        raise _invalid("bundle id")
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None or len(version) > 64:
        raise _invalid("bundle version")
    if source.get("availability") != "installable":
        raise _invalid("availability")
    if community:
        if package_id.startswith("official-") or source.get("review") != "community":
            raise _invalid("community catalog entry")
        if not isinstance(source.get("license"), str) or source["license"] not in LICENSES:
            raise _invalid("license")
        coverage = source.get("coverage")
        style = source.get("style")
        _exact_keys(coverage, {"label", "group", "region_codes"}, set(), "coverage")
        _exact_keys(style, {"id", "name", "category", "tags"}, set(), "style")
        regions = coverage["region_codes"]
        if not isinstance(regions, list) or len(regions) > 32 or any(not isinstance(x, str) or REGION_RE.fullmatch(x) is None for x in regions) or len(set(regions)) != len(regions):
            raise _invalid("region codes")
        if coverage["group"] == "global" and regions:
            raise _invalid("global coverage")
        if not isinstance(coverage["group"], str) or not isinstance(style.get("id"), str) or SAFE_ID.fullmatch(style["id"]) is None:
            raise _invalid("coverage or style")
        _text(style.get("category"), "style category", 30)
        tags = style.get("tags")
        if not isinstance(tags, list) or len(tags) > 16 or any(not isinstance(tag, str) for tag in tags):
            raise _invalid("style tags")
        for tag in tags:
            _text(tag, "style tag", 30)
        if not isinstance(source.get("species"), list) or not 1 <= len(source["species"]) <= MAX_SPECIES or any(not isinstance(x, str) or SCIENTIFIC_RE.fullmatch(x) is None for x in source["species"]) or source["species"] != sorted(set(source["species"])):
            raise _invalid("species list")
        count, archive_bytes = source.get("species_count"), source.get("archive_bytes")
        if isinstance(count, bool) or not isinstance(count, int) or count != len(source["species"]):
            raise _invalid("species count")
        if isinstance(archive_bytes, bool) or not isinstance(archive_bytes, int) or not 1 <= archive_bytes <= MAX_BUNDLE_BYTES:
            raise _invalid("bundle size")
        if not isinstance(source.get("previews"), list) or not 1 <= len(source["previews"]) <= 6:
            raise _invalid("previews")
        previews = [_checked_preview(preview) for preview in source["previews"]]
        result = {
            "id": package_id,
            "version": version,
            "name": name,
            "description": _text(source.get("description"), "description", 260, optional=True),
            "creator": _text(source.get("creator"), "creator", 100),
            "coverage": {"label": _text(coverage["label"], "coverage label", 90), "group": coverage["group"], "region_codes": regions},
            "style": {"id": style.get("id"), "name": _text(style.get("name"), "style name", 90)},
            "species_count": count,
            "species": source["species"],
            "license": source["license"],
            "archive_bytes": archive_bytes,
            "previews": previews,
            "source": "community",
        }
    else:
        if not package_id.startswith("official-"):
            raise _invalid("official bundle id")
        result = {"id": package_id, "version": version, "name": name, "description": "Official AvianVisitors bundle", "creator": "AvianVisitors", "coverage": {"label": "AvianVisitors", "group": "global", "region_codes": []}, "style": {"id": "avianvisitors", "name": "AvianVisitors"}, "species_count": 0, "species": [], "license": "", "source": "official"}
    result["manifest"] = _checked_ref(source.get("manifest"))
    return result


def _parse_catalog(raw: bytes, *, community: bool) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PackageError("AvianVisitors catalog is not valid JSON") from exc
    expected_format = COMMUNITY_FORMAT if community else OFFICIAL_FORMAT
    _exact_keys(payload, {"format", "format_version", "updated", "object_base_url", "packs"}, set(), "catalog")
    if payload.get("format") != expected_format or type(payload.get("format_version")) is not int or payload["format_version"] != 1 or payload.get("object_base_url") != OBJECT_BASE_URL:
        raise _invalid("catalog format")
    updated = payload.get("updated")
    if not isinstance(updated, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}\.\d{3}Z)?", updated) is None:
        raise _invalid("catalog date")
    try:
        date.fromisoformat(updated[:10])
    except ValueError as exc:
        raise _invalid("catalog date") from exc
    packs = payload.get("packs")
    if not isinstance(packs, list) or len(packs) > 1000 or (not community and not packs):
        raise _invalid("catalog pack list")
    result = [_checked_common_row(row, community=community) for row in packs]
    if len({pack["id"] for pack in result}) != len(result):
        raise _invalid("duplicate bundle id")
    return result


async def _get_bytes(client: httpx.AsyncClient, url: str, maximum: int, expected: int | None = None) -> bytes:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise _invalid("download URL") from exc
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.hostname not in {"avianvisitors.com", "raw.githubusercontent.com"} or port not in (None, 443) or parsed.query or parsed.fragment:
        raise _invalid("download URL")
    try:
        async with client.stream("GET", url, headers={"Accept": "application/json,image/png", "Accept-Encoding": "identity"}) as response:
            response.raise_for_status()
            declared = response.headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > maximum or (expected is not None and int(declared) != expected)):
                raise _invalid("download size")
            result = bytearray()
            async for chunk in response.aiter_bytes():
                result.extend(chunk)
                if len(result) > maximum:
                    raise _invalid("download size")
    except httpx.HTTPError as exc:
        raise PackageError(f"Could not fetch AvianVisitors bundle data: {exc}") from exc
    raw = bytes(result)
    if len(raw) > maximum or (expected is not None and len(raw) != expected):
        raise _invalid("download size")
    return raw


async def fetch_avianvisitors_catalog() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        community_raw, official_raw = await asyncio.gather(
            _get_bytes(client, COMMUNITY_CATALOG_URL, MAX_CATALOG_BYTES),
            _get_bytes(client, OFFICIAL_CATALOG_URL, MAX_CATALOG_BYTES),
        )
        community = _parse_catalog(community_raw, community=True)
        official = _parse_catalog(official_raw, community=False)
        async def add_official_details(pack: dict[str, Any]) -> None:
            raw = await _get_bytes(client, pack["manifest"]["url"], MAX_MANIFEST_BYTES, pack["manifest"]["bytes"])
            manifest = _validate_manifest(raw, pack)
            pack["description"] = manifest["description"]
            pack["creator"] = manifest["attribution"]["creator"]
            pack["coverage"] = {"label": manifest["coverage"]["label"], "group": manifest["coverage"]["type"], "region_codes": manifest["coverage"]["region_codes"]}
            pack["style"] = manifest["style"]
            pack["species_count"] = len({item["scientific_name"] for item in manifest["assets"]})
            pack["license"] = manifest["license"]
            pack["archive_bytes"] = manifest["total_bytes"]
        await asyncio.gather(*(add_official_details(pack) for pack in official))
    ids = {pack["id"] for pack in community}
    if ids & {pack["id"] for pack in official}:
        raise _invalid("catalog id collision")
    for item in official + community:
        item["target_id"] = f"avianvisitors-hosted-{item['id']}"
    return sorted(official + community, key=lambda item: (item["source"] != "official", item["name"].casefold()))


def _species_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _pose_suffix(pose_id: str) -> str:
    number = 1 if pose_id == "perched" else 2 if pose_id == "flight" else int(pose_id.removeprefix("variant-"))
    return f"-{number}" if number > 1 else ""


def _validate_manifest(raw: bytes, pack: dict[str, Any]) -> dict[str, Any]:
    if hashlib.sha256(raw).hexdigest() != pack["manifest"]["sha256"]:
        raise PackageError("AvianVisitors manifest checksum does not match the catalog")
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PackageError("AvianVisitors manifest is not valid JSON") from exc
    required = {"format", "format_version", "id", "version", "name", "style", "coverage", "species", "license", "attribution"}
    _exact_keys(manifest, required, {"description", "provenance"}, "manifest")
    version = manifest.get("format_version")
    if manifest.get("format") != MANIFEST_FORMAT or type(version) is not int or version not in {1, 2}:
        raise _invalid("manifest format")
    if manifest.get("id") != pack["id"] or manifest.get("version") != pack["version"]:
        raise PackageError("AvianVisitors manifest identity does not match the catalog")
    style, coverage, license_record, attribution = manifest["style"], manifest["coverage"], manifest["license"], manifest["attribution"]
    _exact_keys(style, {"id", "name"}, set(), "manifest style")
    if not isinstance(style.get("id"), str) or SAFE_ID.fullmatch(style["id"]) is None:
        raise _invalid("manifest style id")
    style = {"id": style["id"], "name": _text(style["name"], "style name", 90)}
    _exact_keys(coverage, {"type", "label"}, {"region_codes"}, "manifest coverage")
    coverage_type = coverage.get("type")
    regions = coverage.get("region_codes", [])
    if not isinstance(coverage_type, str) or coverage_type not in {"region", "global", "selection"} or not isinstance(regions, list) or len(regions) > 32 or any(not isinstance(x, str) or REGION_RE.fullmatch(x) is None for x in regions) or len(set(regions)) != len(regions):
        raise _invalid("manifest coverage")
    if (coverage_type == "region" and not regions) or (coverage_type == "global" and regions):
        raise _invalid("manifest coverage")
    coverage = {"type": coverage_type, "label": _text(coverage.get("label"), "coverage label", 90), "region_codes": regions}
    _exact_keys(license_record, {"spdx"}, {"file"}, "manifest license")
    spdx = license_record.get("spdx")
    if not isinstance(spdx, str) or spdx not in LICENSES or (version == 1 and spdx == "LicenseRef-NoC-US"):
        raise _invalid("manifest license")
    if "file" in license_record and license_record["file"] and (not isinstance(license_record["file"], str) or license_record["file"].startswith("/") or ".." in Path(license_record["file"]).parts):
        raise _invalid("manifest license file")
    _exact_keys(attribution, {"creator"}, {"source_url"}, "manifest attribution")
    attribution_source = attribution.get("source_url", "")
    if attribution_source is None:
        attribution_source = ""
    if not isinstance(attribution_source, str) or len(attribution_source) > 500:
        raise _invalid("source URL")
    if attribution_source:
        try:
            source_url = urlsplit(attribution_source)
        except (TypeError, ValueError) as exc:
            raise _invalid("source URL") from exc
        if not isinstance(attribution_source, str) or source_url.scheme != "https" or not source_url.hostname or source_url.username or source_url.password:
            raise _invalid("source URL")
    attribution = {"creator": _text(attribution.get("creator"), "attribution", 100), "source_url": attribution_source}
    if "provenance" in manifest:
        provenance = manifest["provenance"]
        _exact_keys(provenance, {"method", "review"}, {"model"}, "manifest provenance")
        method, review = provenance.get("method"), provenance.get("review")
        if not isinstance(method, str) or method not in {"manual", "generated", "mixed"} or not isinstance(review, str) or review not in {"human-reviewed", "contributor-reviewed"}:
            raise _invalid("manifest provenance")
        model = _text(provenance.get("model"), "generation model", 100, optional=True)
        if method in {"generated", "mixed"} and not model:
            raise _invalid("manifest provenance")
    name = _text(manifest.get("name"), "bundle name", 90)
    description = _text(manifest.get("description", "Community-maintained bird artwork."), "description", 260, optional=True)
    species = manifest.get("species")
    if not isinstance(species, list) or not 1 <= len(species) <= MAX_SPECIES:
        raise _invalid("manifest species list")
    assets: list[dict[str, Any]] = []
    seen_species: set[str] = set()
    seen_paths: set[str] = set()
    total_bytes = 0
    for bird in species:
        _exact_keys(bird, {"scientific_name", "poses"}, {"common_name"}, "manifest species")
        scientific = _text(bird.get("scientific_name"), "scientific name", 163)
        if SCIENTIFIC_RE.fullmatch(scientific) is None:
            raise _invalid("scientific name")
        slug = _species_slug(scientific)
        if slug in seen_species:
            raise _invalid("duplicate scientific name")
        seen_species.add(slug)
        if "common_name" in bird:
            common_name = _text(bird["common_name"], "common name", 100, optional=True)
        else:
            common_name = ""
        poses = bird.get("poses")
        if not isinstance(poses, list) or not 1 <= len(poses) <= (2 if version == 1 else 32):
            raise _invalid("manifest poses")
        seen_poses: set[str] = set()
        for pose in poses:
            _exact_keys(pose, {"id", "file", "sha256", "bytes"}, set(), "manifest pose")
            pose_id = pose.get("id")
            allowed = POSES_V1 if version == 1 else POSES_V2
            if not isinstance(pose_id, str) or pose_id not in allowed or pose_id in seen_poses:
                raise _invalid("manifest pose id")
            seen_poses.add(pose_id)
            path = f"illustrations/{slug}{_pose_suffix(pose_id)}.png"
            if pose.get("file") != path or path in seen_paths:
                raise _invalid("manifest illustration path")
            seen_paths.add(path)
            digest = _checked_hash(pose.get("sha256"))
            size = pose.get("bytes")
            if isinstance(size, bool) or not isinstance(size, int) or not 67 <= size <= MAX_IMAGE_BYTES:
                raise _invalid("illustration size")
            total_bytes += size
            if total_bytes > MAX_BUNDLE_BYTES:
                raise PackageError("AvianVisitors bundle exceeds the 1 GB limit")
            assets.append({"scientific_name": scientific, "common_name": common_name, "slug": slug, "pose": pose_id, "path": path, "sha256": digest, "bytes": size})
    if pack["source"] == "community":
        if len(species) != pack["species_count"] or [item["scientific_name"] for item in species] != pack["species"] or total_bytes != pack["archive_bytes"]:
            raise PackageError("AvianVisitors manifest metadata does not match the catalog")
        if name != pack["name"] or description != pack["description"] or attribution["creator"] != pack["creator"] or style != pack["style"] or coverage["label"] != pack["coverage"]["label"] or regions != pack["coverage"]["region_codes"] or (coverage_type == "global") != (pack["coverage"]["group"] == "global") or spdx != pack["license"]:
            raise PackageError("AvianVisitors manifest metadata does not match the catalog")
        by_object = {(asset["scientific_name"], asset["pose"]): asset for asset in assets}
        for preview in pack["previews"]:
            match = by_object.get((preview["scientific_name"], preview["pose"]))
            if not match or (preview["common_name"], preview["sha256"], preview["bytes"]) != (match["common_name"], match["sha256"], match["bytes"]):
                raise PackageError("AvianVisitors preview does not match the manifest")
    elif name != pack["name"]:
        raise PackageError("AvianVisitors manifest name does not match the catalog")
    return {"id": pack["id"], "version": pack["version"], "format_version": version, "name": name, "description": description, "style": style, "coverage": coverage, "license": spdx, "attribution": attribution, "assets": assets, "total_bytes": total_bytes}


async def _fetch_object(client: httpx.AsyncClient, asset: dict[str, Any]) -> bytes:
    url = OBJECT_BASE_URL + asset["sha256"] + ".png"
    raw = await _get_bytes(client, url, MAX_IMAGE_BYTES, asset["bytes"])
    if hashlib.sha256(raw).hexdigest() != asset["sha256"]:
        raise PackageError("AvianVisitors illustration checksum does not match the manifest")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or image.width > 4096 or image.height > 4096 or image.width * image.height > 16_000_000:
                raise PackageError("AvianVisitors illustration dimensions are invalid")
            image.load()
    except PackageError:
        raise
    except Exception as exc:
        raise PackageError("AvianVisitors illustration is not a valid PNG") from exc
    return raw


def _remove(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


async def install_avianvisitors_bundle(pack_id: str, destination: Path, progress: Callable[[float, str], None] | None = None) -> dict[str, Any]:
    if not isinstance(pack_id, str) or SAFE_ID.fullmatch(pack_id) is None or len(pack_id) > 80:
        raise PackageError("Invalid AvianVisitors bundle id")
    packs = await fetch_avianvisitors_catalog()
    pack = next((entry for entry in packs if entry["id"] == pack_id), None)
    if pack is None:
        raise PackageError("Bundle is not in the current AvianVisitors catalog")
    target_id = f"avianvisitors-hosted-{pack_id}"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / target_id
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise PackageError("Existing AvianVisitors pack path is unsafe")
    if target.exists():
        manifest_path = target / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 64 * 1024:
            raise PackageError("An existing pack already uses this AvianVisitors bundle ID")
        try:
            existing_metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise PackageError("An existing pack already uses this AvianVisitors bundle ID") from exc
        if not isinstance(existing_metadata, dict) or existing_metadata.get("format") != "birdframe-avianvisitors-hosted-v1" or existing_metadata.get("source_id") != pack_id:
            raise PackageError("An existing AvianAssets pack already uses this AvianVisitors bundle ID")
    stage = Path(tempfile.mkdtemp(prefix=f".{target_id}.staging-", dir=destination))
    backup = destination / f".{target_id}.previous-{uuid.uuid4().hex}"
    try:
        if shutil.disk_usage(destination).free < pack.get("archive_bytes", 0) + 16 * 1024 * 1024:
            raise PackageError("Not enough free space to install this AvianVisitors bundle")
        async with httpx.AsyncClient(timeout=45, follow_redirects=False, limits=httpx.Limits(max_connections=8)) as client:
            raw_manifest = await _get_bytes(client, pack["manifest"]["url"], MAX_MANIFEST_BYTES, pack["manifest"]["bytes"])
            manifest = _validate_manifest(raw_manifest, pack)
            if progress:
                progress(0.0, "downloading")
            completed = 0
            async def download(asset: dict[str, Any]) -> None:
                nonlocal completed
                raw = await _fetch_object(client, asset)
                target_file = stage / asset["path"]
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_bytes(raw)
                completed += 1
                if progress:
                    progress(completed / len(manifest["assets"]), "downloading")
            for offset in range(0, len(manifest["assets"]), 8):
                results = await asyncio.gather(*(download(asset) for asset in manifest["assets"][offset:offset + 8]), return_exceptions=True)
                failure = next((result for result in results if isinstance(result, BaseException)), None)
                if failure is not None:
                    raise failure
        metadata = {
            "package_id": target_id,
            "format": "birdframe-avianvisitors-hosted-v1",
            "source": "https://avianvisitors.com/bundles",
            "source_id": manifest["id"],
            "source_format_version": manifest["format_version"],
            "version": manifest["version"],
            "name": manifest["name"],
            "description": manifest["description"],
            "style": manifest["style"],
            "coverage": manifest["coverage"],
            "license": {"spdx": manifest["license"]},
            "attribution": manifest["attribution"],
        }
        (stage / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _remove(backup)
        if target.exists():
            target.replace(backup)
        try:
            stage.replace(target)
        except Exception:
            if backup.exists() and not target.exists():
                backup.replace(target)
            raise
        _remove(backup)
        if progress:
            progress(1.0, "installing")
        return {"id": target_id, "source_id": pack_id, "name": metadata["name"], "version": metadata["version"], "species": len(manifest["assets"])}
    except Exception:
        _remove(stage)
        raise
