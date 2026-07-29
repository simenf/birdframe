from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .schemas import Detection, PublicSettings


@dataclass(frozen=True)
class SpeciesCount:
    common_name: str
    scientific_name: str
    count: int
    confidence: float
    latest_at: str


@dataclass
class Placement:
    species: SpeciesCount
    image: Image.Image
    x: int
    y: int


PALETTES = {
    "classic": ((74, 57, 41), (174, 112, 48), (50, 72, 99), (163, 61, 44), (110, 119, 82)),
    "muted": ((85, 72, 56), (137, 115, 75), (79, 94, 104), (129, 79, 71), (116, 123, 94)),
    "vivid": ((48, 43, 38), (194, 111, 31), (35, 74, 125), (184, 45, 40), (77, 130, 86)),
}

# BirdWeather commonly supplies English common names.  Keep a local Norwegian
# field-guide vocabulary for the species most likely to occur in Nordic public
# stations; an unknown name falls back gracefully instead of blocking a render.
NORWEGIAN_NAMES = {
    "Apus apus": "tårnseiler", "Pica pica": "skjære", "Turdus merula": "svarttrost",
    "Corvus cornix": "kråke", "Corvus corax": "ravn", "Sturnus vulgaris": "stær",
    "Passer domesticus": "gråspurv", "Columba palumbus": "ringdue", "Erithacus rubecula": "rødstrupe",
    "Parus major": "kjøttmeis", "Cyanistes caeruleus": "blåmeis", "Aegithalos caudatus": "stjertmeis",
    "Lophophanes cristatus": "toppmeis", "Periparus ater": "svartmeis", "Poecile montanus": "granmeis",
    "Poecile palustris": "løvmeis", "Fringilla coelebs": "bokfink", "Chloris chloris": "grønnfink",
    "Carduelis carduelis": "stillits", "Spinus spinus": "grønnsisik", "Pyrrhula pyrrhula": "dompap",
    "Turdus pilaris": "gråtrost", "Turdus iliacus": "rødvingetrost", "Turdus philomelos": "måltrost",
    "Turdus viscivorus": "duetrost", "Motacilla alba": "linerle", "Hirundo rustica": "låvesvale",
    "Delichon urbicum": "taksvale", "Phylloscopus trochilus": "løvsanger", "Phylloscopus collybita": "gransanger",
    "Ficedula hypoleuca": "svarthvit fluesnapper", "Muscicapa striata": "grå fluesnapper",
    "Dryobates major": "flaggspett", "Picus viridis": "grønnspett", "Accipiter nisus": "spurvehauk",
    "Buteo buteo": "musvåk", "Falco tinnunculus": "tårnfalk", "Anas platyrhynchos": "stokkand",
    "Cygnus olor": "knoppsvane", "Larus canus": "fiskemåke",
}


def group_detections(detections: Iterable[Detection]) -> list[SpeciesCount]:
    grouped: dict[str, list[Detection]] = {}
    for detection in detections:
        key = detection.scientific_name or detection.common_name
        grouped.setdefault(key, []).append(detection)
    results = []
    for values in grouped.values():
        latest = max(values, key=lambda item: item.detected_at)
        results.append(SpeciesCount(
            common_name=latest.common_name,
            scientific_name=latest.scientific_name,
            count=len(values),
            confidence=max(item.confidence for item in values),
            latest_at=latest.detected_at.isoformat(),
        ))
    return sorted(results, key=lambda item: (-item.count, item.common_name.casefold()))


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 6:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    return (242, 228, 201)


def _asset_path(art_dir: Path, species: SpeciesCount, pose: str) -> Path:
    safe = "".join(character.lower() if character.isalnum() else "-" for character in (species.scientific_name or species.common_name)).strip("-")
    return art_dir / "species" / safe / f"{pose}.png"


def _demo_bird(species: SpeciesCount, pose: str, palette_name: str) -> Image.Image:
    """A graceful deterministic placeholder used until approved generated art exists."""
    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    colors = PALETTES.get(palette_name, PALETTES["classic"])
    seed = int(hashlib.sha256(f"{species.common_name}:{pose}".encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    body = colors[seed % len(colors)]
    wing = colors[(seed // 7) % len(colors)]
    accent = colors[(seed // 13) % len(colors)]
    if pose == "flight":
        draw.polygon([(470, 560), (120, 175), (370, 330), (505, 450)], fill=wing)
        draw.polygon([(520, 560), (900, 175), (650, 330), (515, 450)], fill=wing)
        draw.ellipse((375, 395, 650, 700), fill=body, outline=(46, 38, 30), width=12)
        draw.polygon([(485, 660), (520, 875), (565, 660)], fill=accent)
        draw.polygon([(625, 480), (780, 520), (630, 550)], fill=(46, 38, 30))
    else:
        draw.ellipse((360, 240, 680, 760), fill=body, outline=(46, 38, 30), width=12)
        draw.ellipse((420, 145, 655, 405), fill=accent, outline=(46, 38, 30), width=12)
        draw.polygon([(620, 275), (810, 315), (635, 350)], fill=(46, 38, 30))
        draw.polygon([(410, 425), (350, 710), (530, 640), (590, 420)], fill=wing)
        draw.line((470, 740, 450, 830), fill=(46, 38, 30), width=14)
        draw.line((560, 740, 580, 830), fill=(46, 38, 30), width=14)
    draw.ellipse((560, 242, 586, 268), fill=(20, 16, 12))
    # a few intentional woodblock-like stroke accents, never feather texture
    for offset in range(3):
        x = 410 + offset * 55 + rng.randrange(-10, 10)
        draw.arc((x, 430, x + 125, 650), 215, 310, fill=(46, 38, 30), width=8)
    return image


def load_species_asset(art_dir: Path, species: SpeciesCount, pose: str, palette: str) -> Image.Image:
    candidate = _asset_path(art_dir, species, pose)
    if candidate.exists():
        with Image.open(candidate) as asset:
            return asset.convert("RGBA")
    safe = "".join(character.lower() if character.isalnum() else "-" for character in (species.scientific_name or species.common_name)).strip("-")
    package_root = art_dir / "packages"
    if package_root.exists():
        for package in sorted(package_root.iterdir()):
            packaged = package / "assets" / "species" / safe / f"{pose}.png"
            if packaged.exists():
                with Image.open(packaged) as asset:
                    return asset.convert("RGBA")
    return _demo_bird(species, pose, palette)


def _resize_for_area(asset: Image.Image, area: float) -> Image.Image:
    ratio = asset.width / asset.height
    width = max(1, int(math.sqrt(area * ratio)))
    height = max(1, int(math.sqrt(area / ratio)))
    return asset.resize((width, height), Image.Resampling.LANCZOS)


def _mask(asset: Image.Image, scale: int = 8) -> Image.Image:
    alpha = asset.getchannel("A")
    width = max(1, math.ceil(alpha.width / scale))
    height = max(1, math.ceil(alpha.height / scale))
    return alpha.resize((width, height), Image.Resampling.NEAREST).point(lambda value: 255 if value > 32 else 0)


def _collides(occupancy: Image.Image, asset: Image.Image, x: int, y: int, scale: int) -> bool:
    mask = _mask(asset, scale)
    x_small = x // scale
    y_small = y // scale
    if x_small < 0 or y_small < 0 or x_small + mask.width > occupancy.width or y_small + mask.height > occupancy.height:
        return True
    crop = occupancy.crop((x_small, y_small, x_small + mask.width, y_small + mask.height))
    return any(left and right for left, right in zip(crop.getdata(), mask.getdata()))


def _occupy(occupancy: Image.Image, asset: Image.Image, x: int, y: int, scale: int) -> None:
    mask = _mask(asset, scale)
    occupancy.paste(255, (x // scale, y // scale), mask)


def _try_pack(items: list[tuple[SpeciesCount, Image.Image]], width: int, height: int, margin: int, seed: int) -> list[Placement] | None:
    scale = 8
    occupancy = Image.new("L", (math.ceil(width / scale), math.ceil(height / scale)), 0)
    rng = random.Random(seed)
    placements: list[Placement] = []
    # A shuffled, aspect-aware grid makes every species claim a part of the
    # canvas.  The former single-origin spiral concentrated birds in the middle.
    count = max(1, len(items))
    columns = max(1, math.ceil(math.sqrt(count * width / height)))
    rows = math.ceil(count / columns)
    cells = [(column, row) for row in range(rows) for column in range(columns)]
    rng.shuffle(cells)
    for index, (species, asset) in enumerate(items):
        column, row = cells[index]
        target_x = margin + (column + 0.5) * (width - 2 * margin) / columns
        target_y = margin + (row + 0.5) * (height - 2 * margin) / rows
        candidates = [(int(target_x - asset.width / 2), int(target_y - asset.height / 2))]
        for step in range(1, 2600):
            angle = step * 0.42 + rng.random() * 0.015
            radius = 5.2 * math.sqrt(step)
            x = int(target_x + radius * 1.45 * math.cos(angle) - asset.width / 2)
            y = int(target_y + radius * 0.90 * math.sin(angle) - asset.height / 2)
            candidates.append((x, y))
        chosen: tuple[int, int] | None = None
        for x, y in candidates:
            if x < margin or y < margin or x + asset.width > width - margin or y + asset.height > height - margin:
                continue
            if not _collides(occupancy, asset, x, y, scale):
                chosen = (x, y)
                break
        if chosen is None:
            return None
        _occupy(occupancy, asset, chosen[0], chosen[1], scale)
        placements.append(Placement(species, asset, *chosen))
    return placements


def _font(size: int, *, italic: bool = False) -> ImageFont.ImageFont:
    names = (
        "/usr/share/fonts/truetype/texgyre/texgyrepagella-italic.otf",
        "TeXGyrePagella-Italic.otf", "DejaVuSerif-Italic.ttf", "DejaVuSerif.ttf",
    ) if italic else (
        "/usr/share/fonts/truetype/texgyre/texgyrepagella-regular.otf",
        "TeXGyrePagella-Regular.otf", "DejaVuSerif.ttf",
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _norwegian_name(species: SpeciesCount) -> str:
    return NORWEGIAN_NAMES.get(species.scientific_name, species.common_name)


def _draw_number(draw: ImageDraw.ImageDraw, x: int, y: int, number: int, paper: tuple[int, int, int]) -> None:
    radius = 27
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=paper, outline=(74, 57, 41), width=3)
    text = str(number)
    font = _font(30)
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2 - 2), text, fill=(74, 57, 41), font=font)


def _draw_legend(canvas: Image.Image, placements: list[Placement], start_x: int, paper: tuple[int, int, int], script_size: str) -> None:
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    draw.line((start_x, 88, start_x, height - 88), fill=(130, 108, 77), width=2)
    scale = {"small": 0.82, "medium": 1.0, "large": 1.22}[script_size]
    title_font, name_font, latin_font = _font(int(42 * scale), italic=True), _font(int(31 * scale), italic=True), _font(int(22 * scale), italic=True)
    draw.text((start_x + 42, 94), "Dagens fugler", fill=(74, 57, 41), font=title_font)
    available = height - 205
    row_height = max(int(62 * scale), min(int(104 * scale), available // max(1, len(placements))))
    for number, placement in enumerate(placements, start=1):
        y = 174 + (number - 1) * row_height
        _draw_number(draw, start_x + 62, y + 22, number, paper)
        draw.text((start_x + 106, y), _norwegian_name(placement.species), fill=(74, 57, 41), font=name_font)
        draw.text((start_x + 106, y + 34), placement.species.scientific_name or placement.species.common_name, fill=(110, 90, 65), font=latin_font)


def collage_image(species: list[SpeciesCount], settings: PublicSettings, art_dir: Path) -> tuple[Image.Image, list[dict[str, object]]]:
    width, height = settings.output_width, settings.output_height
    canvas = Image.new("RGB", (width, height), _hex_rgb(settings.paper_tone))
    if not species:
        draw = ImageDraw.Draw(canvas)
        draw.text((width // 2 - 130, height // 2), "Waiting for birds…", fill=(74, 57, 41), font=None)
        return canvas, []
    paper = _hex_rgb(settings.paper_tone)
    avian_style = settings.collage_style == "avianvisitors_horizontal"
    legend_width = int(width * (0.26 if avian_style else 0.28)) if settings.labels_enabled else 0
    art_width = width - legend_width
    density = {"sparse": 0.52, "standard": 0.68, "full": 0.80}[settings.collage_density]
    if avian_style:
        density = min(0.84, density + 0.06)
    # Counts should influence prominence, not turn a frequent bird into a giant.
    scores = [1 + 0.15 * math.log1p(max(1, item.count)) for item in species]
    area_budget = art_width * height * density
    seed = int(hashlib.sha256("|".join(item.common_name for item in species).encode()).hexdigest()[:16], 16)
    prepared: list[tuple[SpeciesCount, Image.Image]] = []
    for index, item in enumerate(species):
        if settings.pose_preference == "balanced":
            pose = "flight" if (seed + index) % 2 else "perched"
        else:
            pose = settings.pose_preference
        asset = load_species_asset(art_dir, item, pose, settings.palette)
        prepared.append((item, _resize_for_area(asset, area_budget * scores[index] / sum(scores))))
    prepared.sort(key=lambda pair: pair[1].width * pair[1].height, reverse=True)
    margin = max(36, int(min(width, height) * 0.035))
    header_height = int(height * 0.085) if avian_style else 0
    placements = None
    for shrink in range(10):
        factor = 0.93 ** shrink
        scaled = [(item, asset.resize((max(1, int(asset.width * factor)), max(1, int(asset.height * factor))), Image.Resampling.LANCZOS)) for item, asset in prepared]
        placements = _try_pack(scaled, art_width, height - header_height, margin, seed)
        if placements:
            if header_height:
                placements = [Placement(item.species, item.image, item.x, item.y + header_height) for item in placements]
            break
    if not placements:
        # a guaranteed, bounded fallback keeps an art image available even for huge species lists
        placements = []
        for index, (item, asset) in enumerate(prepared[:12]):
            scale = min(0.35, 0.75 / math.sqrt(len(prepared[:12])))
            image = asset.resize((int(asset.width * scale), int(asset.height * scale)), Image.Resampling.LANCZOS)
            x = margin + (index % 4) * (art_width - 2 * margin) // 4 + 24
            y = header_height + margin + (index // 4) * (height - header_height - 2 * margin) // 3 + 24
            placements.append(Placement(item, image, x, y))
    if avian_style:
        draw = ImageDraw.Draw(canvas)
        inset = max(24, min(width, height) // 60)
        draw.rectangle((inset, inset, art_width - inset, height - inset), outline=(128, 103, 72), width=max(2, inset // 10))
        title = _font(max(23, int(height * 0.027)), italic=True)
        subtitle = _font(max(15, int(height * 0.016)), italic=True)
        draw.text((margin * 1.5, inset * 1.2), "Avian Visitors", fill=(74, 57, 41), font=title)
        draw.text((margin * 1.5, inset * 1.2 + int(height * 0.034)), "A horizontal field plate", fill=(110, 90, 65), font=subtitle)
    for number, placement in enumerate(placements, start=1):
        canvas.paste(placement.image, (placement.x, placement.y), placement.image)
        if settings.labels_enabled:
            visible = placement.image.getchannel("A").getbbox() or (0, 0, placement.image.width, placement.image.height)
            marker_x = placement.x + max(28, visible[0] - 16)
            marker_y = placement.y + max(28, visible[1] - 16)
            _draw_number(ImageDraw.Draw(canvas), marker_x, marker_y, number, paper)
    species_data = [{"common_name": item.species.common_name, "scientific_name": item.species.scientific_name,
                     "count": item.species.count, "confidence": item.species.confidence,
                     "latest_at": item.species.latest_at, "x": item.x, "y": item.y,
                     "width": item.image.width, "height": item.image.height} for item in placements]
    if settings.labels_enabled:
        _draw_legend(canvas, placements, art_width, paper, settings.legend_script_size)
    return canvas, species_data


def latest_visitor_image(species: list[SpeciesCount], settings: PublicSettings, art_dir: Path) -> tuple[Image.Image, list[dict[str, object]]]:
    width, height = settings.output_width, settings.output_height
    canvas = Image.new("RGB", (width, height), _hex_rgb(settings.paper_tone))
    if not species:
        return collage_image([], settings, art_dir)
    bird = max(species, key=lambda item: item.latest_at)
    pose = "perched" if settings.pose_preference == "balanced" else settings.pose_preference
    asset = load_species_asset(art_dir, bird, pose, settings.palette)
    max_height = int(height * 0.82)
    max_width = int(width * 0.62)
    ratio = min(max_width / asset.width, max_height / asset.height)
    asset = asset.resize((int(asset.width * ratio), int(asset.height * ratio)), Image.Resampling.LANCZOS)
    x, y = (width - asset.width) // 2, (height - asset.height) // 2
    canvas.paste(asset, (x, y), asset)
    if settings.labels_enabled:
        draw = ImageDraw.Draw(canvas)
        draw.text((48, height - 100), bird.common_name, fill=(74, 57, 41))
        if bird.scientific_name:
            draw.text((48, height - 60), bird.scientific_name, fill=(110, 90, 65))
    return canvas, [{"common_name": bird.common_name, "scientific_name": bird.scientific_name, "count": bird.count,
                     "confidence": bird.confidence, "latest_at": bird.latest_at, "x": x, "y": y,
                     "width": asset.width, "height": asset.height}]
