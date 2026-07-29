import io
import json
import zipfile
from pathlib import Path

import pytest

from birdframe.packages import PackageError, install_archive


def zip_bytes(files: dict[str, bytes]) -> io.BytesIO:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    result.seek(0)
    return result


def test_installs_avianvisitors_layout_and_generates_manifest(tmp_path: Path):
    archive = tmp_path / "pack.zip"
    archive.write_bytes(zip_bytes({
        "illustrations/turdus-merula.png": b"png",
        "sketches/turdus-merula.png": b"png",
        "dims.json": b"{}",
        "masks.json": b"{}",
    }).getvalue())
    result = install_archive(archive, "community-pack", tmp_path / "installed")
    assert result["id"] == "community-pack"
    manifest = json.loads((tmp_path / "installed/community-pack/manifest.json").read_text())
    assert manifest["format"] == "avianvisitors-v1"
    assert (tmp_path / "installed/community-pack/illustrations/turdus-merula.png").exists()


def test_rejects_unsafe_archive_path(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    archive.write_bytes(zip_bytes({"../escape.txt": b"no"}).getvalue())
    with pytest.raises(PackageError, match="unsafe archive path"):
        install_archive(archive, "unsafe-pack", tmp_path / "installed")
