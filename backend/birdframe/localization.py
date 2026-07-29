from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=8)
def load_species_names(locale: str = "no") -> dict[str, str]:
    """Load a scientific-name keyed locale file, returning an empty map if absent."""
    path = Path(__file__).parent / "data" / f"{locale.lower().replace('-', '_')}_names.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def localized_species_name(scientific_name: str, fallback: str, locale: str = "no") -> str:
    normalized = " ".join(scientific_name.split())
    names = load_species_names(locale)
    return names.get(normalized, fallback)
