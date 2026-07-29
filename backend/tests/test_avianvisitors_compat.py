from pathlib import Path

from PIL import Image

from birdframe.compositor import SpeciesCount, collage_image, load_species_asset
from birdframe.packages import _avianvisitors_manifest
from birdframe.schemas import PublicSettings


def test_loads_unmodified_avianvisitors_illustration_names(tmp_path: Path):
    illustrations = tmp_path / "packages" / "community-set" / "illustrations"
    illustrations.mkdir(parents=True)
    Image.new("RGBA", (20, 10), (12, 34, 56, 255)).save(illustrations / "apus-apus.png")
    Image.new("RGBA", (10, 20), (65, 43, 21, 255)).save(illustrations / "apus-apus-2.png")
    species = SpeciesCount("Common Swift", "Apus apus", 1, 1, "")
    assert load_species_asset(tmp_path, species, "perched", "classic").size == (20, 10)
    assert load_species_asset(tmp_path, species, "flight", "classic").size == (10, 20)


def test_selected_pack_and_sketch_treatment_are_honoured(tmp_path: Path):
    species = SpeciesCount("Common Swift", "Apus apus", 1, 1, "")
    root = tmp_path / "packages" / "regional-pack" / "avian" / "assets"
    (root / "illustrations").mkdir(parents=True)
    (root / "sketches").mkdir()
    Image.new("RGBA", (20, 10), (12, 34, 56, 255)).save(root / "illustrations" / "apus-apus.png")
    Image.new("RGBA", (7, 19), (65, 43, 21, 255)).save(root / "sketches" / "apus-apus.png")

    asset = load_species_asset(tmp_path, species, "perched", "classic", "regional-pack", "sketches")
    assert asset.size == (7, 19)


def test_accepts_avianvisitors_bundle_without_a_birdframe_manifest(tmp_path: Path):
    illustrations = tmp_path / "illustrations"
    illustrations.mkdir()
    Image.new("RGBA", (4, 4)).save(illustrations / "apus-apus.png")
    (tmp_path / "dims.json").write_text("{}")
    (tmp_path / "masks.json").write_text("{}")
    metadata = _avianvisitors_manifest(tmp_path, "community-set")
    assert metadata == {
        "package_id": "community-set", "format": "avianvisitors-v1",
        "illustrations": "illustrations", "dims": "dims.json", "masks": "masks.json",
    }


def test_avianvisitors_original_layout_renders_a_landscape_collage(tmp_path: Path):
    image, species = collage_image(
        [
            SpeciesCount("Common Swift", "Apus apus", 5, 1, "2026-01-01T00:00:00Z"),
            SpeciesCount("Eurasian Magpie", "Pica pica", 2, 1, "2026-01-01T00:00:00Z"),
            SpeciesCount("Eurasian Blackbird", "Turdus merula", 1, 1, "2026-01-01T00:00:00Z"),
        ],
        PublicSettings(output_width=640, output_height=360, collage_style="avianvisitors_exact"),
        tmp_path,
    )
    assert image.size == (640, 360)
    assert len(species) == 3
