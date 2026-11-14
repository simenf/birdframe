from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from birdframe.compositor import SpeciesCount, _draw_number, _handwritten_name_asset, collage_image, load_species_asset, species_has_asset
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


def test_handwritten_label_stays_clear_of_a_steep_silhouette():
    bird = Image.new("RGBA", (320, 180), (0, 0, 0, 0))
    ImageDraw.Draw(bird).polygon([(10, 140), (80, 90), (150, 105), (295, 10), (260, 160)], fill=(70, 100, 130, 255))
    result = _handwritten_name_asset(bird, "Common Chaffinch", (30, 20, 10))
    offset = result.info["birdframe_art_offset_y"]
    assert offset >= 0
    bird_at_offset = Image.new("RGBA", result.size, (0, 0, 0, 0))
    bird_at_offset.alpha_composite(bird, (0, offset))
    difference = ImageChops.difference(result, bird_at_offset).getchannel("A")
    assert difference.getbbox()  # The name was actually drawn.
    assert not ImageChops.multiply(difference, bird_at_offset.getchannel("A")).getbbox()


def test_marker_number_scales_with_the_circle():
    for radius in (10, 60):
        canvas = Image.new("RGB", (radius * 4, radius * 4), "white")
        _draw_number(ImageDraw.Draw(canvas), radius * 2, radius * 2, 8,
                     (255, 255, 255), (0, 0, 0), radius)
        interior = canvas.crop((int(radius * 1.5), int(radius * 1.5),
                                int(radius * 2.5), int(radius * 2.5))).convert("L")
        bounds = ImageChops.invert(interior).getbbox()
        assert bounds is not None
        assert bounds[3] - bounds[1] >= radius * 0.45


def test_pack_art_is_found_under_an_older_scientific_name(tmp_path: Path):
    illustrations = tmp_path / "packages" / "western-na" / "illustrations"
    illustrations.mkdir(parents=True)
    Image.new("RGBA", (20, 10), (12, 34, 56, 255)).save(illustrations / "accipiter-cooperii.png")
    Image.new("RGBA", (10, 20), (65, 43, 21, 255)).save(illustrations / "accipiter-cooperii-2.png")
    species = SpeciesCount("Cooper's Hawk", "Astur cooperii", 1, 1, "")

    assert species_has_asset(tmp_path, species)
    assert load_species_asset(tmp_path, species, "perched", "classic").size == (20, 10)
    assert load_species_asset(tmp_path, species, "flight", "classic").size == (10, 20)


def test_aliases_work_in_both_directions_and_prefer_the_detected_name(tmp_path: Path):
    illustrations = tmp_path / "packages" / "mixed" / "illustrations"
    illustrations.mkdir(parents=True)
    Image.new("RGBA", (20, 10)).save(illustrations / "hesperiphona-vespertina.png")
    Image.new("RGBA", (7, 7)).save(illustrations / "coccothraustes-vespertinus.png")

    newer = SpeciesCount("Evening Grosbeak", "Hesperiphona vespertina", 1, 1, "")
    older = SpeciesCount("Evening Grosbeak", "Coccothraustes vespertinus", 1, 1, "")
    assert load_species_asset(tmp_path, newer, "perched", "classic").size == (20, 10)
    assert load_species_asset(tmp_path, older, "perched", "classic").size == (7, 7)

    (illustrations / "coccothraustes-vespertinus.png").unlink()
    assert load_species_asset(tmp_path, older, "perched", "classic").size == (20, 10)


def test_generated_art_beats_pack_art_found_through_an_alias(tmp_path: Path):
    illustrations = tmp_path / "packages" / "western-na" / "illustrations"
    illustrations.mkdir(parents=True)
    Image.new("RGBA", (20, 10)).save(illustrations / "accipiter-cooperii.png")
    generated = tmp_path / "species" / "astur-cooperii"
    generated.mkdir(parents=True)
    Image.new("RGBA", (5, 9)).save(generated / "perched.png")
    species = SpeciesCount("Cooper's Hawk", "Astur cooperii", 1, 1, "")

    assert load_species_asset(tmp_path, species, "perched", "classic").size == (5, 9)


def test_unaliased_species_without_art_still_falls_back(tmp_path: Path):
    (tmp_path / "packages" / "western-na" / "illustrations").mkdir(parents=True)
    species = SpeciesCount("Common Swift", "Apus apus", 1, 1, "")
    assert not species_has_asset(tmp_path, species)
    assert load_species_asset(tmp_path, species, "perched", "classic").size == (1024, 1024)
