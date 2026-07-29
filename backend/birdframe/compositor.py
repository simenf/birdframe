from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .schemas import Detection, PublicSettings
from .localization import localized_species_name


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


def load_species_asset(
    art_dir: Path, species: SpeciesCount, pose: str, palette: str,
    package_id: str = "all", asset_variant: str = "illustrations",
) -> Image.Image:
    candidate = _asset_path(art_dir, species, pose)
    if candidate.exists():
        with Image.open(candidate) as asset:
            return asset.convert("RGBA")
    safe = "".join(character.lower() if character.isalnum() else "-" for character in (species.scientific_name or species.common_name)).strip("-")
    package_root = art_dir / "packages"
    if package_root.exists():
        packages = sorted(package_root.iterdir())
        if package_id != "all":
            packages = [package for package in packages if package.name == package_id]
        for package in packages:
            candidates = [package / "assets" / "species" / safe / f"{pose}.png"]
            # AvianVisitors bundles use scientific-name slugs directly:
            # <slug>.png is perched, <slug>-2.png is the flight pose.
            avian_slug = f"{safe}{'-2' if pose == 'flight' else ''}.png"
            candidates.extend((
                package / "illustrations" / avian_slug,
                package / "assets" / "illustrations" / avian_slug,
                package / "avian" / "assets" / "illustrations" / avian_slug,
            ))
            if asset_variant == "sketches":
                sketch_candidates = (
                    package / "sketches" / avian_slug,
                    package / "assets" / "sketches" / avian_slug,
                    package / "avian" / "assets" / "sketches" / avian_slug,
                )
                candidates = list(sketch_candidates) + candidates
            for packaged in candidates:
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


def _try_pack_avianvisitors(items: list[tuple[SpeciesCount, Image.Image]], width: int, height: int, margin: int, seed: int) -> list[Placement] | None:
    """Landscape, silhouette-aware centre-out nester matching AvianVisitors' layout discipline."""
    scale, padding = 4, 3
    occupancy = Image.new("L", (math.ceil(width / scale), math.ceil(height / scale)), 0)
    rng = random.Random(seed)
    ordered = sorted(items, key=lambda pair: pair[1].width * pair[1].height, reverse=True)
    placements: list[Placement] = []

    def place(asset: Image.Image, x: int, y: int) -> None:
        mask = _mask(asset, scale).filter(ImageFilter.MaxFilter(padding * 2 + 1))
        occupancy.paste(255, (x // scale, y // scale), mask)

    for index, (species, asset) in enumerate(ordered):
        if index == 0:
            selected = ((width - asset.width) // 2, (height - asset.height) // 2)
        else:
            total_area = sum(item.image.width * item.image.height for item in placements) or 1
            com_x = sum((item.x + item.image.width / 2) * item.image.width * item.image.height for item in placements) / total_area
            com_y = sum((item.y + item.image.height / 2) * item.image.width * item.image.height for item in placements) / total_area
            selected: tuple[int, int] | None = None
            best_cost = float("inf")
            phase = rng.random() * math.tau
            max_radius = max(width, height)
            step = max(scale, min(asset.width, asset.height) * 0.05)
            for radius_index in range(max(1, int(max_radius / step))):
                radius = radius_index * step
                samples = max(36, int(radius / 1.6))
                found = False
                for sample in range(samples):
                    theta = phase + sample / samples * math.tau
                    x = int(width / 2 + radius * 2.1 * math.cos(theta) - asset.width / 2)
                    y = int(height / 2 + radius * math.sin(theta) - asset.height / 2)
                    if x < margin or y < margin or x + asset.width > width - margin or y + asset.height > height - margin:
                        continue
                    if _collides(occupancy, asset, x, y, scale):
                        continue
                    cost = math.hypot((x + asset.width / 2 - com_x) / 2.1, y + asset.height / 2 - com_y) + rng.random() * step * 0.5
                    if cost < best_cost:
                        selected, best_cost, found = (x, y), cost, True
                if found:
                    break
            if selected is None:
                return None
        x, y = selected
        if x < margin or y < margin or x + asset.width > width - margin or y + asset.height > height - margin:
            return None
        place(asset, x, y)
        placements.append(Placement(species, asset, x, y))
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


def _script_font(size: int) -> ImageFont.ImageFont:
    """A restrained copperplate-like hand for the natural-history legend."""
    for name in (
        "/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf",
        "Z003-MediumItalic.otf", "URW Chancery L Italic", "DejaVuSerif-Italic.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _localized_name(species: SpeciesCount, locale: str) -> str:
    return localized_species_name(species.scientific_name, species.common_name, locale)


def _draw_number(draw: ImageDraw.ImageDraw, x: int, y: int, number: int, paper: tuple[int, int, int], radius: int = 27) -> None:
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=paper, outline=(74, 57, 41), width=3)
    text = str(number)
    font = _font(max(18, int(radius * 1.1)))
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2 - 2), text, fill=(74, 57, 41), font=font)


def _marker_position(placement: Placement, birds: Image.Image, markers: Image.Image, width: int, height: int, margin: int, radius: int) -> tuple[int, int, int, int] | None:
    """Place a clear-paper marker, consistently starting at ten o'clock."""
    clearance = max(10, radius // 2)
    visible = placement.image.getchannel("A").getbbox() or (0, 0, placement.image.width, placement.image.height)
    left, top = placement.x + visible[0], placement.y + visible[1]
    right, bottom = placement.x + visible[2], placement.y + visible[3]
    centre_x, centre_y = (left + right) // 2, (top + bottom) // 2
    candidates: list[tuple[int, int]] = []
    # A fixed clockwise order keeps the visual language consistent across every
    # composition. Wider rings preserve a safe option in a crowded cluster.
    for distance in (radius + clearance, radius * 2 + clearance, radius * 3 + clearance):
        for angle in (-135, -90, -45, 0, 45, 90, 135, 180):
            radians = math.radians(angle)
            candidates.append((int(centre_x + math.cos(radians) * (max(right - left, bottom - top) / 2 + distance)), int(centre_y + math.sin(radians) * (max(right - left, bottom - top) / 2 + distance))))
    # A busy plate can exhaust the immediate halo. Search the remaining paper
    # in a stable near-to-far order, keeping the marker unambiguously linked by
    # the leader line drawn by the caller.
    stride = radius * 2 + clearance
    distant = [
        (x, y)
        for y in range(margin + radius, height - margin - radius + 1, stride)
        for x in range(margin + radius, width - margin - radius + 1, stride)
    ]
    candidates.extend(sorted(distant, key=lambda point: (point[0] - centre_x) ** 2 + (point[1] - centre_y) ** 2))
    circle = Image.new("L", (radius * 2 + 1, radius * 2 + 1), 0)
    ImageDraw.Draw(circle).ellipse((0, 0, radius * 2, radius * 2), fill=255)
    for x, y in candidates:
        box = (x - radius, y - radius, x + radius + 1, y + radius + 1)
        if box[0] < margin or box[1] < margin or box[2] > width - margin or box[3] > height - margin:
            continue
        bird_crop, marker_crop = birds.crop(box), markers.crop(box)
        if not ImageChops.multiply(bird_crop, circle).getbbox() and not ImageChops.multiply(marker_crop, circle).getbbox():
            markers.paste(255, (box[0], box[1]), circle)
            anchor_x = min(max(x, left), right)
            anchor_y = min(max(y, top), bottom)
            return x, y, anchor_x, anchor_y
    return None


def _draw_legend(canvas: Image.Image, placements: list[Placement], start_x: int, paper: tuple[int, int, int], script_size: str, locale: str) -> None:
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    draw.line((start_x, 88, start_x, height - 88), fill=(130, 108, 77), width=2)
    scale = {"small": 0.82, "medium": 1.0, "large": 1.22}[script_size]
    available = height - 205
    row_height = max(32, min(int(104 * scale), available // max(1, len(placements))))
    # Fit the pen-script to the row rather than allowing lower legend entries
    # to run off a 16:9 panel on a busy day.
    fitted_scale = min(scale, row_height / 62)
    title_font = _script_font(int(42 * min(scale, 1.0)))
    name_font, latin_font = _script_font(max(13, int(33 * fitted_scale))), _font(max(11, int(22 * fitted_scale)), italic=True)
    draw.text((start_x + 42, 94), "Dagens fugler", fill=(74, 57, 41), font=title_font)
    for number, placement in enumerate(placements, start=1):
        y = 174 + (number - 1) * row_height
        _draw_number(draw, start_x + 62, y + 22, number, paper)
        draw.text((start_x + 106, y), _localized_name(placement.species, locale), fill=(74, 57, 41), font=name_font)
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
    avian_exact = settings.collage_style == "avianvisitors_exact"
    legend_width = int(width * (0.26 if avian_style else 0.28)) if settings.labels_enabled else 0
    art_width = width - legend_width
    density = {"sparse": 0.52, "standard": 0.68, "full": 0.80}[settings.collage_density]
    if avian_style:
        density = min(0.84, density + 0.06)
    # Counts should influence prominence, not turn a frequent bird into a giant.
    scores = [max(1, item.count) ** (0.65 if avian_exact else 0.15) for item in species]
    if avian_exact:
        count = len(species)
        density = 0.72 if count <= 4 else 0.65 if count <= 12 else 0.55 if count <= 24 else 0.46
    # Numbered plates need deliberate breathing room around each silhouette.
    # It is better to use slightly smaller birds than to compromise a callout
    # by drawing it across feathers or a face.
    if settings.labels_enabled:
        density *= 0.78
    area_budget = art_width * height * density
    seed = int(hashlib.sha256("|".join(item.common_name for item in species).encode()).hexdigest()[:16], 16)
    prepared: list[tuple[SpeciesCount, Image.Image]] = []
    for index, item in enumerate(species):
        if settings.pose_preference == "balanced":
            pose = "flight" if (seed + index) % 2 else "perched"
        else:
            pose = settings.pose_preference
        asset = load_species_asset(art_dir, item, pose, settings.palette, settings.asset_pack_id, settings.asset_variant)
        area = area_budget * scores[index] / sum(scores)
        if avian_exact:
            minimum = art_width * height * (0.010 if len(species) <= 8 else 0.0075 if len(species) <= 20 else 0.0055)
            area = max(minimum, area)
        prepared.append((item, _resize_for_area(asset, area)) )
    prepared.sort(key=lambda pair: pair[1].width * pair[1].height, reverse=True)
    margin = max(36, int(min(width, height) * 0.035))
    header_height = int(height * 0.085) if avian_style else 0
    placements = None
    for shrink in range(10):
        factor = 0.93 ** shrink
        scaled = [(item, asset.resize((max(1, int(asset.width * factor)), max(1, int(asset.height * factor))), Image.Resampling.LANCZOS)) for item, asset in prepared]
        pack = _try_pack_avianvisitors if avian_exact else _try_pack
        placements = pack(scaled, art_width, height - header_height, margin, seed)
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
    bird_occupancy = Image.new("L", (art_width, height), 0)
    for placement in placements:
        bird_occupancy.paste(255, (placement.x, placement.y), placement.image.getchannel("A"))
    for placement in placements:
        canvas.paste(placement.image, (placement.x, placement.y), placement.image)
    if settings.labels_enabled:
        marker_data: list[tuple[int, int, int, int, int]] = []
        # Retry the full set at progressively smaller, still legible sizes.
        # A failed search never falls back to an overlapping marker.
        for radius in range(max(18, 28 - len(placements) // 6), 16, -2):
            marker_occupancy = Image.new("L", (art_width, height), 0)
            candidate_data: list[tuple[int, int, int, int, int]] = []
            for number, placement in enumerate(placements, start=1):
                position = _marker_position(placement, bird_occupancy, marker_occupancy, art_width, height, margin, radius)
                if position is None:
                    break
                candidate_data.append((number, *position))
            if len(candidate_data) == len(placements):
                marker_data = candidate_data
                break
        draw = ImageDraw.Draw(canvas)
        for number, marker_x, marker_y, _anchor_x, _anchor_y in marker_data:
            _draw_number(draw, marker_x, marker_y, number, paper, radius)
    species_data = [{"common_name": item.species.common_name, "scientific_name": item.species.scientific_name,
                     "count": item.species.count, "confidence": item.species.confidence,
                     "latest_at": item.species.latest_at, "x": item.x, "y": item.y,
                     "width": item.image.width, "height": item.image.height} for item in placements]
    if settings.labels_enabled:
        _draw_legend(canvas, placements, art_width, paper, settings.legend_script_size, settings.language)
    return canvas, species_data


def latest_visitor_image(species: list[SpeciesCount], settings: PublicSettings, art_dir: Path) -> tuple[Image.Image, list[dict[str, object]]]:
    width, height = settings.output_width, settings.output_height
    canvas = Image.new("RGB", (width, height), _hex_rgb(settings.paper_tone))
    if not species:
        return collage_image([], settings, art_dir)
    bird = max(species, key=lambda item: item.latest_at)
    pose = "perched" if settings.pose_preference == "balanced" else settings.pose_preference
    asset = load_species_asset(art_dir, bird, pose, settings.palette, settings.asset_pack_id, settings.asset_variant)
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
