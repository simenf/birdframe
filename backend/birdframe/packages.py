from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


class PackageError(RuntimeError):
    pass


MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


def _avianvisitors_manifest(staging: Path, package_id: str) -> dict[str, Any] | None:
    """Recognise an unmodified AvianVisitors illustration bundle.

    Community bundles conventionally contain transparent
    ``illustrations/<scientific-slug>.png`` + ``-2.png`` pairs and the
    accompanying ``dims.json`` / ``masks.json`` tables, but no BirdFrame
    manifest. Keep their layout intact and add only our small metadata file.
    """
    candidates = (
        staging / "illustrations",
        staging / "assets" / "illustrations",
        staging / "avian" / "assets" / "illustrations",
    )
    illustrations = next((item for item in candidates if item.is_dir() and any(item.glob("*.png"))), None)
    if illustrations is None:
        return None
    metadata: dict[str, Any] = {
        "package_id": package_id,
        "format": "avianvisitors-v1",
        "illustrations": str(illustrations.relative_to(staging)),
    }
    for table in ("dims.json", "masks.json"):
        paths = (staging / table, staging / "frontend" / table, staging / "avian" / "frontend" / table)
        found = next((item for item in paths if item.is_file()), None)
        if found:
            metadata[table.removesuffix(".json")] = str(found.relative_to(staging))
    (staging / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def _https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise PackageError("Package catalog and downloads must use HTTPS")
    return value


async def fetch_catalog(url: str) -> list[dict[str, Any]]:
    _https_url(url)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PackageError(f"Could not fetch artwork catalog: {exc}") from exc
    items = payload.get("packages") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise PackageError("Catalog must be a JSON array or an object with a packages array")
    valid: list[dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        package_id = entry.get("id")
        download = entry.get("download_url")
        digest = entry.get("sha256")
        if isinstance(package_id, str) and SAFE_ID.fullmatch(package_id) and isinstance(download, str) and isinstance(digest, str) and re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            valid.append(entry)
    return valid


def install_archive(archive: Path, package_id: str, destination: Path) -> dict[str, Any]:
    if not SAFE_ID.fullmatch(package_id):
        raise PackageError("Invalid package id")
    destination.mkdir(parents=True, exist_ok=True)
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise PackageError("Package archive exceeds the 500 MB limit")
    with tempfile.TemporaryDirectory(prefix="birdframe-package-") as temporary:
        staging = Path(temporary) / "staging"
        staging.mkdir()
        try:
            bundle = zipfile.ZipFile(archive)
        except (OSError, zipfile.BadZipFile) as exc:
            raise PackageError("Package is not a valid ZIP archive") from exc
        with bundle:
            total = 0
            for item in bundle.infolist():
                name = Path(item.filename)
                unix_mode = item.external_attr >> 16
                is_symlink = (unix_mode & 0o170000) == 0o120000
                if name.is_absolute() or ".." in name.parts or is_symlink:
                    raise PackageError("Package contains an unsafe archive path")
                if item.is_dir():
                    continue
                total += item.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise PackageError("Package expands beyond the 1 GB safety limit")
                if name.suffix.lower() not in {".json", ".png", ".jpg", ".jpeg", ".webp", ".md", ".txt", ".license"}:
                    raise PackageError(f"Unsupported file in package: {name.name}")
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        manifest = staging / "manifest.json"
        generated_manifest = _avianvisitors_manifest(staging, package_id) if not manifest.exists() else None
        if not manifest.exists():
            raise PackageError("Package is missing manifest.json and is not an AvianVisitors illustration bundle")
        try:
            metadata = json.loads(manifest.read_text())
        except json.JSONDecodeError as exc:
            raise PackageError("Package manifest is invalid JSON") from exc
        if not isinstance(metadata, dict) or not metadata.get("package_id"):
            raise PackageError("Package manifest is missing package_id")
        target = destination / package_id
        replacement = destination / f".{package_id}.new"
        shutil.rmtree(replacement, ignore_errors=True)
        shutil.copytree(staging, replacement)
        if target.exists():
            backup = destination / f".{package_id}.previous"
            shutil.rmtree(backup, ignore_errors=True)
            target.replace(backup)
            replacement.replace(target)
            shutil.rmtree(backup, ignore_errors=True)
        else:
            replacement.replace(target)
        return {"id": package_id, "path": str(target), "manifest": metadata}


async def install_package(entry: dict[str, Any], destination: Path) -> dict[str, Any]:
    package_id = str(entry.get("id", ""))
    if not SAFE_ID.fullmatch(package_id):
        raise PackageError("Invalid package id")
    download_url = _https_url(str(entry.get("download_url", "")))
    expected = str(entry.get("sha256", "")).lower()
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise PackageError("Package is missing a valid SHA-256")
    with tempfile.TemporaryDirectory(prefix="birdframe-package-download-") as temporary:
        archive = Path(temporary) / "package.zip"
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()
                    written = 0
                    with archive.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            written += len(chunk)
                            if written > MAX_ARCHIVE_BYTES:
                                raise PackageError("Package archive exceeds the 500 MB limit")
                            output.write(chunk)
        except httpx.HTTPError as exc:
            raise PackageError(f"Could not download package: {exc}") from exc
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != expected:
            raise PackageError("Package checksum does not match the catalog")
        return install_archive(archive, package_id, destination)


async def install_package_url(url: str, package_id: str, destination: Path) -> dict[str, Any]:
    """Download and install a direct HTTPS ZIP URL without a catalog."""
    _https_url(url)
    if not SAFE_ID.fullmatch(package_id):
        raise PackageError("Invalid package id")
    with tempfile.TemporaryDirectory(prefix="birdframe-package-download-") as temporary:
        archive = Path(temporary) / "package.zip"
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    written = 0
                    with archive.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            written += len(chunk)
                            if written > MAX_ARCHIVE_BYTES:
                                raise PackageError("Package archive exceeds the 500 MB limit")
                            output.write(chunk)
        except httpx.HTTPError as exc:
            raise PackageError(f"Could not download package: {exc}") from exc
        return install_archive(archive, package_id, destination)
