from datetime import UTC, datetime, timedelta
from pathlib import Path

from birdframe.storage import Store


def _insert_composition(store: Store, *, revision: int, created_at: datetime, path: Path) -> None:
    with store.connection() as db:
        db.execute(
            """INSERT INTO compositions(revision, mode, width, height, path, sha256, species_json, created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (revision, "collage", 640, 360, str(path), "0" * 64, "[]", created_at.isoformat()),
        )


def _insert_log(store: Store, created_at: datetime, message: str = "test event") -> None:
    with store.connection() as db:
        db.execute("INSERT INTO logs(level,message,created_at) VALUES('INFO',?,?)", (message, created_at.isoformat()))


def _insert_tv_upload(store: Store, composition_id: int, content_id: str, created_at: datetime) -> None:
    with store.connection() as db:
        db.execute(
            "INSERT INTO tv_uploads(composition_id,content_id,created_at) VALUES(?,?,?)",
            (composition_id, content_id, created_at.isoformat()),
        )


def _revisions(store: Store) -> list[int]:
    with store.connection() as db:
        return [row["revision"] for row in db.execute("SELECT revision FROM compositions ORDER BY revision")]


def _log_count(store: Store) -> int:
    with store.connection() as db:
        return int(db.execute("SELECT COUNT(*) FROM logs").fetchone()[0])


def test_cleanup_keeps_one_composition_per_day_for_one_year(tmp_path: Path):
    store = Store(tmp_path)
    now = datetime.now(UTC)
    files: dict[int, Path] = {}

    def add(revision: int, when: datetime) -> None:
        path = tmp_path / f"composition-{revision}.jpg"
        path.write_bytes(b"jpeg")
        files[revision] = path
        _insert_composition(store, revision=revision, created_at=when, path=path)

    add(1, now - timedelta(days=400))            # older than the retention window
    add(2, now - timedelta(days=2, hours=1))     # same day as 3, older revision
    add(3, now - timedelta(days=2))              # latest of that day: kept
    add(4, now - timedelta(days=1))
    add(5, now)                                  # today's/current composition: always kept
    _insert_tv_upload(store, 2, "OLD001", now - timedelta(days=2))
    _insert_tv_upload(store, 5, "CUR001", now)
    _insert_log(store, now - timedelta(days=40))
    _insert_log(store, now - timedelta(days=1))

    result = store.cleanup()

    assert result == {"compositions": 2, "files": 2, "logs": 1}
    assert _revisions(store) == [3, 4, 5]
    assert not files[1].exists() and not files[2].exists()
    assert files[3].exists() and files[4].exists() and files[5].exists()
    assert _log_count(store) == 1
    with store.connection() as db:
        remaining = [row["content_id"] for row in db.execute("SELECT content_id FROM tv_uploads")]
    assert remaining == ["CUR001"]


def test_cleanup_is_idempotent_and_tolerates_missing_files(tmp_path: Path):
    store = Store(tmp_path)
    now = datetime.now(UTC)
    missing = tmp_path / "composition-ghost.jpg"  # row exists but file was already removed
    _insert_composition(store, revision=1, created_at=now - timedelta(days=400), path=missing)
    _insert_log(store, now - timedelta(days=100))

    first = store.cleanup()
    second = store.cleanup()

    assert first["compositions"] == 1 and first["files"] == 0 and first["logs"] == 1
    assert second == {"compositions": 0, "files": 0, "logs": 0}
    assert _revisions(store) == []
