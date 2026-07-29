from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from cryptography.fernet import Fernet

from .schemas import Detection, DetectionCreate, PublicSettings, SettingsResponse, SettingsUpdate


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    """Small, dependency-free persistent store for a single BirdFrame install."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.art_dir = self.data_dir / "art"
        self.art_dir.mkdir(exist_ok=True)
        key_file = self.data_dir / "secret.key"
        if not key_file.exists():
            key_file.write_bytes(Fernet.generate_key())
            os.chmod(key_file, 0o600)
        self.crypt = Fernet(key_file.read_bytes())
        self.db_path = self.data_dir / "birdframe.db"
        self._init_db()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_db(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (
                  key TEXT PRIMARY KEY, value TEXT NOT NULL, secret INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS detections (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_type TEXT NOT NULL,
                  source_event_id TEXT NOT NULL DEFAULT '',
                  common_name TEXT NOT NULL,
                  scientific_name TEXT NOT NULL DEFAULT '',
                  species_code TEXT NOT NULL DEFAULT '',
                  confidence REAL NOT NULL,
                  detected_at TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  UNIQUE(source_type, source_event_id)
                );
                CREATE TABLE IF NOT EXISTS compositions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  revision INTEGER NOT NULL UNIQUE,
                  mode TEXT NOT NULL,
                  width INTEGER NOT NULL,
                  height INTEGER NOT NULL,
                  path TEXT NOT NULL,
                  sha256 TEXT NOT NULL,
                  species_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  tv_confirmed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS jobs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  kind TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
                  result_json TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tv_uploads (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  composition_id INTEGER NOT NULL,
                  content_id TEXT NOT NULL UNIQUE,
                  created_at TEXT NOT NULL
                );
                """
            )

    def get_settings(self) -> SettingsResponse:
        values = PublicSettings().model_dump()
        secrets: set[str] = set()
        with self.connection() as db:
            for row in db.execute("SELECT key, value, secret FROM settings"):
                if row["secret"]:
                    secrets.add(row["key"])
                elif row["key"] in values:
                    values[row["key"]] = json.loads(row["value"])
        return SettingsResponse(
            **values,
            has_openrouter_api_key="openrouter_api_key" in secrets,
            has_birdweather_token="birdweather_token" in secrets,
            has_ebird_api_key="ebird_api_key" in secrets,
            has_display_api_token="display_api_token" in secrets,
        )

    def save_settings(self, incoming: SettingsUpdate) -> SettingsResponse:
        data = incoming.model_dump()
        secret_names = {"openrouter_api_key", "birdweather_token", "ebird_api_key", "display_api_token"}
        with self.connection() as db:
            for key, value in data.items():
                if key in secret_names:
                    if value is not None:
                        encrypted = self.crypt.encrypt(value.encode()).decode()
                        db.execute("INSERT OR REPLACE INTO settings(key,value,secret) VALUES(?,?,1)", (key, encrypted))
                else:
                    db.execute("INSERT OR REPLACE INTO settings(key,value,secret) VALUES(?,?,0)", (key, json.dumps(value)))
        return self.get_settings()

    def secret(self, key: str) -> str | None:
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key=? AND secret=1", (key,)).fetchone()
        return self.crypt.decrypt(row["value"].encode()).decode() if row else None

    def add_detection(self, payload: DetectionCreate) -> Detection | None:
        occurred = (payload.detected_at or datetime.now(UTC)).astimezone(UTC)
        created = datetime.now(UTC)
        source_id = payload.source_event_id or f"manual-{payload.common_name}-{occurred.isoformat()}"
        with self.connection() as db:
            try:
                cursor = db.execute(
                    """INSERT INTO detections(source_type,source_event_id,common_name,scientific_name,species_code,confidence,detected_at,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (payload.source_type, source_id, payload.common_name, payload.scientific_name,
                     payload.species_code, payload.confidence, occurred.isoformat(), created.isoformat()),
                )
            except sqlite3.IntegrityError:
                return None
            identifier = int(cursor.lastrowid)
        data = payload.model_dump()
        data["detected_at"] = occurred
        return Detection(**data, id=identifier, created_at=created)

    def recent_detections(self, hours: int, limit: int = 500) -> list[Detection]:
        cutoff = datetime.now(UTC).timestamp() - hours * 3600
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM detections WHERE unixepoch(detected_at)>=? ORDER BY detected_at DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        return [Detection(
            id=row["id"], source_type=row["source_type"], source_event_id=row["source_event_id"],
            common_name=row["common_name"], scientific_name=row["scientific_name"], species_code=row["species_code"],
            confidence=row["confidence"], detected_at=datetime.fromisoformat(row["detected_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        ) for row in rows]

    def add_composition(self, *, mode: str, width: int, height: int, path: Path, sha256: str, species: list[dict[str, Any]]) -> int:
        with self.connection() as db:
            revision = int(db.execute("SELECT COALESCE(MAX(revision),0)+1 AS revision FROM compositions").fetchone()["revision"])
            cursor = db.execute(
                "INSERT INTO compositions(revision,mode,width,height,path,sha256,species_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (revision, mode, width, height, str(path), sha256, json.dumps(species), utcnow()),
            )
            return int(cursor.lastrowid)

    def current_composition(self) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM compositions ORDER BY revision DESC LIMIT 1").fetchone()
        if not row:
            return None
        result = dict(row)
        result["species"] = json.loads(result.pop("species_json"))
        result["tv_confirmed"] = bool(result["tv_confirmed"])
        return result

    def create_job(self, kind: str, payload: dict[str, Any]) -> int:
        now = utcnow()
        with self.connection() as db:
            cursor = db.execute(
                "INSERT INTO jobs(kind,status,payload_json,created_at,updated_at) VALUES(?,?,?,?,?)",
                (kind, "queued", json.dumps(payload), now, now),
            )
            return int(cursor.lastrowid)

    def update_job(self, identifier: int, *, status: str, result: dict[str, Any] | None = None, error: str = "") -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE jobs SET status=?, result_json=?, error=?, updated_at=? WHERE id=?",
                (status, json.dumps(result or {}), error, utcnow(), identifier),
            )

    def jobs(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 100").fetchall()
        return [dict(row) | {"payload": json.loads(row["payload_json"]), "result": json.loads(row["result_json"])} for row in rows]

    def record_tv_upload(self, composition_id: int, content_id: str) -> str | None:
        """Record a successful owned upload and return the prior owned content id."""
        with self.connection() as db:
            old = db.execute("SELECT content_id FROM tv_uploads ORDER BY id DESC LIMIT 1").fetchone()
            db.execute("INSERT OR IGNORE INTO tv_uploads(composition_id,content_id,created_at) VALUES(?,?,?)", (composition_id, content_id, utcnow()))
            db.execute("UPDATE compositions SET tv_confirmed=1 WHERE id=?", (composition_id,))
        return old["content_id"] if old and old["content_id"] != content_id else None
