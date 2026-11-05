from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

SOURCE_PRIORITY = {"manual": 100, "kykyemek": 80, "kykyurtmenu": 60, "syrblo": 40}


def _connect() -> sqlite3.Connection:
    path = Path(settings.database_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS menus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT NOT NULL,
                city_slug TEXT NOT NULL,
                meal TEXT NOT NULL,
                menu_date TEXT NOT NULL,
                items_json TEXT NOT NULL,
                calories INTEGER,
                source TEXT NOT NULL,
                source_url TEXT,
                fetched_at TEXT NOT NULL,
                UNIQUE(city_slug, meal, menu_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_status (
                source TEXT PRIMARY KEY,
                last_attempt TEXT,
                last_success TEXT,
                last_error TEXT,
                records_saved INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS city_sync (
                city_slug TEXT NOT NULL,
                menu_date TEXT NOT NULL,
                last_attempt TEXT,
                last_success TEXT,
                last_error TEXT,
                PRIMARY KEY(city_slug, menu_date)
            )
        """)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "city": row["city"],
        "city_slug": row["city_slug"],
        "meal": row["meal"],
        "date": row["menu_date"],
        "items": json.loads(row["items_json"]),
        "calories": row["calories"],
        "source": row["source"],
        "source_url": row["source_url"],
        "fetched_at": row["fetched_at"],
    }


def upsert_menu(record: dict[str, Any], city_slug: str) -> bool:
    source = record.get("source", "unknown")
    fetched_at = record.get("fetched_at") or datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT source FROM menus WHERE city_slug=? AND meal=? AND menu_date=?",
            (city_slug, record["meal"], record["date"]),
        ).fetchone()
        if existing:
            old_priority = SOURCE_PRIORITY.get(existing["source"], 0)
            new_priority = SOURCE_PRIORITY.get(source, 0)
            if new_priority < old_priority:
                return False
        conn.execute("""
            INSERT INTO menus(city, city_slug, meal, menu_date, items_json, calories, source, source_url, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(city_slug, meal, menu_date) DO UPDATE SET
                city=excluded.city,
                items_json=excluded.items_json,
                calories=excluded.calories,
                source=excluded.source,
                source_url=excluded.source_url,
                fetched_at=excluded.fetched_at
        """, (
            record["city"], city_slug, record["meal"], record["date"],
            json.dumps(record["items"], ensure_ascii=False), record.get("calories"),
            source, record.get("source_url"), fetched_at,
        ))
        return True


def get_menu(city_slug: str, meal: str, menu_date: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM menus WHERE city_slug=? AND meal=? AND menu_date=?",
            (city_slug, meal, menu_date),
        ).fetchone()
    return _row_to_dict(row)


def get_month(city_slug: str, year: int, month: int) -> list[dict[str, Any]]:
    prefix = f"{year:04d}-{month:02d}-"
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM menus WHERE city_slug=? AND menu_date LIKE ? ORDER BY menu_date, meal",
            (city_slug, prefix + "%"),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_city_sync(city_slug: str, menu_date: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM city_sync WHERE city_slug=? AND menu_date=?",
            (city_slug, menu_date),
        ).fetchone()
    return dict(row) if row else None


def mark_city_sync(city_slug: str, menu_date: str, success: bool, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("""
            INSERT INTO city_sync(city_slug, menu_date, last_attempt, last_success, last_error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(city_slug, menu_date) DO UPDATE SET
                last_attempt=excluded.last_attempt,
                last_success=CASE WHEN excluded.last_success IS NOT NULL THEN excluded.last_success ELSE city_sync.last_success END,
                last_error=excluded.last_error
        """, (city_slug, menu_date, now, now if success else None, error))


def mark_source(source: str, success: bool, saved: int = 0, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("""
            INSERT INTO source_status(source, last_attempt, last_success, last_error, records_saved)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                last_attempt=excluded.last_attempt,
                last_success=CASE WHEN excluded.last_success IS NOT NULL THEN excluded.last_success ELSE source_status.last_success END,
                last_error=excluded.last_error,
                records_saved=excluded.records_saved
        """, (source, now, now if success else None, error, saved))


def get_source_status() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM source_status ORDER BY source").fetchall()
    return [dict(row) for row in rows]
