from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from cryptography.fernet import Fernet

from .auth import verify_password
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
                CREATE TABLE IF NOT EXISTS logs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  level TEXT NOT NULL,
                  message TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  is_admin INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL REFERENCES users(id),
                  name TEXT NOT NULL,
                  key_hash TEXT NOT NULL UNIQUE,
                  prefix TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  last_used_at TEXT
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

    def needs_setup(self) -> bool:
        """True on first run, before the setup wizard has saved any settings."""
        with self.connection() as db:
            row = db.execute("SELECT 1 FROM settings LIMIT 1").fetchone()
        return row is None

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

    def recent_detections(self, hours: int, limit: int = 500, min_confidence: float = 0.0) -> list[Detection]:
        cutoff = datetime.now(UTC).timestamp() - hours * 3600
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM detections WHERE unixepoch(detected_at)>=? AND confidence>=? ORDER BY detected_at DESC LIMIT ?",
                (cutoff, min_confidence, limit),
            ).fetchall()
        return [Detection(
            id=row["id"], source_type=row["source_type"], source_event_id=row["source_event_id"],
            common_name=row["common_name"], scientific_name=row["scientific_name"], species_code=row["species_code"],
            confidence=row["confidence"], detected_at=datetime.fromisoformat(row["detected_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        ) for row in rows]

    def detections_since(self, cutoff: datetime, *, limit: int | None = None, min_confidence: float = 0.0) -> list[Detection]:
        """Detections at or after an absolute cutoff (e.g. local midnight for the journal)."""
        sql = "SELECT * FROM detections WHERE unixepoch(detected_at)>=? AND confidence>=? ORDER BY detected_at DESC"
        params: list[Any] = [cutoff.timestamp(), min_confidence]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.connection() as db:
            rows = db.execute(sql, params).fetchall()
        return [Detection(
            id=row["id"], source_type=row["source_type"], source_event_id=row["source_event_id"],
            common_name=row["common_name"], scientific_name=row["scientific_name"], species_code=row["species_code"],
            confidence=row["confidence"], detected_at=datetime.fromisoformat(row["detected_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        ) for row in rows]

    def has_recent_species_detection(self, species_key: str, since: datetime, min_confidence: float = 0.0) -> bool:
        """True when a detection of the species exists at or after ``since``.

        Used by the display policy's per-species duplicate cooldown. The key is
        the scientific name when present, otherwise the common name, matching
        :func:`birdframe.compositor.group_detections`.
        """
        with self.connection() as db:
            row = db.execute(
                """SELECT 1 FROM detections
                   WHERE (scientific_name=? OR (scientific_name='' AND common_name=?))
                     AND detected_at>=? AND confidence>=?
                   LIMIT 1""",
                (species_key, species_key, since.astimezone(UTC).isoformat(), min_confidence),
            ).fetchone()
        return row is not None

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

    def log(self, level: str, message: str) -> None:
        """Persist concise, credential-free operational events for the web UI."""
        with self.connection() as db:
            db.execute("INSERT INTO logs(level,message,created_at) VALUES(?,?,?)", (level.upper(), message[:2000], utcnow()))

    def logs(self, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, str | int]], int]:
        with self.connection() as db:
            rows = db.execute("SELECT id,level,message,created_at FROM logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            total = int(db.execute("SELECT COUNT(*) FROM logs").fetchone()[0])
        return [dict(row) for row in rows], total

    def record_tv_upload(self, composition_id: int, content_id: str) -> str | None:
        """Record a successful owned upload and return the prior owned content id."""
        with self.connection() as db:
            old = db.execute("SELECT content_id FROM tv_uploads ORDER BY id DESC LIMIT 1").fetchone()
            db.execute("INSERT OR IGNORE INTO tv_uploads(composition_id,content_id,created_at) VALUES(?,?,?)", (composition_id, content_id, utcnow()))
            db.execute("UPDATE compositions SET tv_confirmed=1 WHERE id=?", (composition_id,))
        return old["content_id"] if old and old["content_id"] != content_id else None

    def latest_tv_upload(self) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT composition_id,content_id,created_at FROM tv_uploads ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def cleanup(self, *, keep_days: int = 365, log_days: int = 30) -> dict[str, int]:
        """Prune old state to bound disk and database growth.

        Keeps at most one composition (the latest of each day) for the last
        ``keep_days`` days and removes logs older than ``log_days`` days.
        Files are unlinked before rows so a crash between the two is healed by
        the next run, and the newest composition is always kept so the current
        display artifact and its TV upload record survive cleanup.
        """
        now = datetime.now(UTC)
        window_start = now - timedelta(days=keep_days)
        removed: list[tuple[int, str]] = []
        kept_days: set[str] = set()
        with self.connection() as db:
            for row in db.execute("SELECT id, path, created_at FROM compositions ORDER BY revision DESC").fetchall():
                created = datetime.fromisoformat(row["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                day = created.date().isoformat()
                if created < window_start or day in kept_days:
                    removed.append((row["id"], row["path"]))
                else:
                    kept_days.add(day)
        removed_files = 0
        for _identifier, path in removed:
            try:
                Path(path).unlink()
                removed_files += 1
            except FileNotFoundError:
                pass
        with self.connection() as db:
            for identifier, _path in removed:
                db.execute("DELETE FROM compositions WHERE id=?", (identifier,))
                db.execute("DELETE FROM tv_uploads WHERE composition_id=?", (identifier,))
            log_cutoff = (now - timedelta(days=log_days)).isoformat()
            log_cursor = db.execute("DELETE FROM logs WHERE created_at < ?", (log_cutoff,))
            removed_logs = log_cursor.rowcount
        return {"compositions": len(removed), "files": removed_files, "logs": removed_logs}

    def user_count(self) -> int:
        with self.connection() as db:
            row = db.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0])

    def create_user(self, username: str, password_hash: str, *, is_admin: bool = False) -> dict[str, Any]:
        with self.connection() as db:
            try:
                cursor = db.execute(
                    "INSERT INTO users(username,password_hash,is_admin,created_at) VALUES(?,?,?,?)",
                    (username, password_hash, int(is_admin), utcnow()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Username is already taken") from exc
            identifier = int(cursor.lastrowid)
        return self.get_user(identifier)

    def get_user(self, identifier: int) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (identifier,)).fetchone()
        return self._user_row(dict(row)) if row else {}

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return self._user_row(dict(row)) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [self._user_row(dict(row)) for row in rows]

    def verify_login(self, username: str, password: str) -> dict[str, Any] | None:
        user = self.get_user_by_username(username)
        if user is None or not verify_password(password, user["password_hash"]):
            return None
        return user

    def create_api_key(self, user_id: int, name: str, key_hash: str, prefix: str) -> dict[str, Any]:
        with self.connection() as db:
            cursor = db.execute(
                "INSERT INTO api_keys(user_id,name,key_hash,prefix,created_at) VALUES(?,?,?,?,?)",
                (user_id, name, key_hash, prefix, utcnow()),
            )
            identifier = int(cursor.lastrowid)
        return self.get_api_key(identifier)

    def get_api_key(self, identifier: int) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM api_keys WHERE id=?", (identifier,)).fetchone()
        return self._api_key_row(dict(row)) if row else {}

    def list_api_keys(self, user_id: int) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM api_keys WHERE user_id=? ORDER BY id", (user_id,)).fetchall()
        return [self._api_key_row(dict(row)) for row in rows]

    def revoke_api_key(self, user_id: int, identifier: int) -> bool:
        with self.connection() as db:
            cursor = db.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (identifier, user_id))
        return cursor.rowcount > 0

    def revoke_api_key_by_hash(self, key_hash: str) -> bool:
        with self.connection() as db:
            cursor = db.execute("DELETE FROM api_keys WHERE key_hash=?", (key_hash,))
        return cursor.rowcount > 0

    def user_for_api_key(self, key_hash: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT users.* FROM api_keys JOIN users ON users.id=api_keys.user_id WHERE api_keys.key_hash=?",
                (key_hash,),
            ).fetchone()
        return self._user_row(dict(row)) if row else None

    def touch_api_key_usage(self, key_hash: str, now: datetime | None = None) -> None:
        stamp = (now or datetime.now(UTC)).isoformat()
        with self.connection() as db:
            db.execute(
                "UPDATE api_keys SET last_used_at=? WHERE key_hash=? AND (last_used_at IS NULL OR last_used_at < ?)",
                (stamp, key_hash, stamp),
            )

    @staticmethod
    def _user_row(row: dict[str, Any]) -> dict[str, Any]:
        row["is_admin"] = bool(row["is_admin"])
        return row

    @staticmethod
    def _api_key_row(row: dict[str, Any]) -> dict[str, Any]:
        return row
