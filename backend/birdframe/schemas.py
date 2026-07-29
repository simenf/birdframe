from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PublicSettings(BaseModel):
    location_label: str = ""
    latitude: float | None = None
    longitude: float | None = None
    timezone: str = "UTC"
    language: str = "en"
    detection_source: Literal["birdweather", "birdweather_public", "birdnet_go"] = "birdweather_public"
    birdnet_go_url: str = "http://birdnet-go:8080"
    birdweather_public_station_id: int | None = Field(default=None, ge=1)
    birdweather_poll_seconds: int = Field(default=15, ge=10, le=3600)
    display_mode: Literal["collage", "latest_visitor"] = "collage"
    collage_hours: int = Field(default=24, ge=1, le=8760)
    confidence_threshold: float = Field(default=0.8, ge=0, le=1)
    duplicate_cooldown_minutes: int = Field(default=5, ge=0, le=1440)
    tv_host: str = ""
    tv_mac: str = ""
    tv_matte: str = "none"
    tv_auto_update_enabled: bool = True
    tv_wake_enabled: bool = False
    tv_quiet_hours_start: str = ""
    tv_quiet_hours_end: str = ""
    tv_update_minutes: int = Field(default=5, ge=1, le=1440)
    output_width: int = Field(default=3840, ge=640, le=7680)
    output_height: int = Field(default=2160, ge=360, le=4320)
    labels_enabled: bool = False
    legend_script_size: Literal["small", "medium", "large"] = "medium"
    collage_style: Literal["classic", "avianvisitors_horizontal"] = "classic"
    paper_tone: str = "#f2e4c9"
    palette: Literal["classic", "muted", "vivid"] = "classic"
    collage_density: Literal["sparse", "standard", "full"] = "standard"
    pose_preference: Literal["balanced", "perched", "flight"] = "balanced"
    package_catalog_url: str = ""
    display_api_enabled: bool = True
    display_api_require_token: bool = False
    occurrence_provider: Literal["birdnet_range", "ebird", "birdweather_history"] = "birdweather_history"
    occurrence_threshold: float = Field(default=0.01, ge=0, le=1)
    occurrence_max_species: int = Field(default=100, ge=1, le=1000)
    occurrence_season: Literal["current", "all_year"] = "current"
    custom_prompt_addendum: str = Field(default="", max_length=4000)
    openrouter_model: str = Field(default="", max_length=250)


class SettingsUpdate(PublicSettings):
    openrouter_api_key: str | None = Field(default=None, min_length=1)
    birdweather_token: str | None = Field(default=None, min_length=1)
    ebird_api_key: str | None = Field(default=None, min_length=1)
    display_api_token: str | None = Field(default=None, min_length=16)


class SettingsResponse(PublicSettings):
    has_openrouter_api_key: bool = False
    has_birdweather_token: bool = False
    has_ebird_api_key: bool = False
    has_display_api_token: bool = False


class DetectionCreate(BaseModel):
    common_name: str = Field(min_length=1, max_length=250)
    scientific_name: str = Field(default="", max_length=250)
    species_code: str = Field(default="", max_length=64)
    confidence: float = Field(default=1, ge=0, le=1)
    detected_at: datetime | None = None
    source_type: Literal["birdweather", "birdweather_public", "birdnet_go", "manual"] = "manual"
    source_event_id: str = ""


class Detection(DetectionCreate):
    id: int
    created_at: datetime


class CompositionSummary(BaseModel):
    id: int
    revision: int
    created_at: datetime
    mode: str
    width: int
    height: int
    sha256: str
    species: list[dict[str, object]]
    tv_confirmed: bool = False


class JobRequest(BaseModel):
    species: list[dict[str, str]] = Field(default_factory=list)
    poses: Literal["one", "both"] = "both"
    model: str = ""


class PackageInstallRequest(BaseModel):
    package_id: str = Field(min_length=1, max_length=128)


class SourceTestRequest(BaseModel):
    source: Literal["birdweather", "birdweather_public", "birdnet_go"]
    url: str = ""
    token: str = ""
    station_id: int | None = Field(default=None, ge=1)
