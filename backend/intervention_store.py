"""
intervention_store.py — Item 3.3
Tracks user-recorded interventions and measures before/after activity score changes.
Uses the same SQLite WAL-mode database as history_store.
"""
import sqlite3
import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = os.environ.get("HISTORY_DB_PATH", str(DATA_DIR / "polynexus_history.db"))


def _get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialise the interventions table (idempotent)."""
    with _get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interventions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id         TEXT NOT NULL,
                recorded_at     TEXT NOT NULL,
                intervention    TEXT NOT NULL,
                applied_at      TEXT,
                notes           TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_interventions_zone ON interventions(zone_id, recorded_at);"
        )


def record_intervention(
    zone_id: str,
    intervention: str,
    applied_at: str | None = None,
    notes: str | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Record a new intervention. Returns the new row id."""
    now = datetime.now(timezone.utc).isoformat()
    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO interventions (zone_id, recorded_at, intervention, applied_at, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (zone_id, now, intervention, applied_at, notes),
        )
        return cursor.lastrowid


def get_interventions(zone_id: str, db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """List all interventions for a zone with before/after score info."""
    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM interventions WHERE zone_id = ? ORDER BY recorded_at DESC",
                (zone_id,),
            ).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["before_after"] = get_before_after(zone_id, row["id"], db_path=db_path)
                results.append(item)
            return results
    except Exception as exc:
        log.error("Failed to get interventions for %s: %s", zone_id, exc)
        return []


def get_before_after(
    zone_id: str, intervention_id: int, db_path: str = DEFAULT_DB_PATH
) -> dict[str, Any] | None:
    """Return the zone_run immediately before and most recent after the intervention date."""
    try:
        with _get_connection(db_path) as conn:
            # Get the intervention's recorded_at timestamp
            iv = conn.execute(
                "SELECT * FROM interventions WHERE id = ? AND zone_id = ?",
                (intervention_id, zone_id),
            ).fetchone()
            if not iv:
                return None

            pivot = iv["applied_at"] or iv["recorded_at"]

            before = conn.execute(
                """
                SELECT id, analysed_at, activity_score, overall_stress
                FROM zone_runs
                WHERE zone_id = ? AND analysed_at < ?
                ORDER BY analysed_at DESC
                LIMIT 1
                """,
                (zone_id, pivot),
            ).fetchone()

            after = conn.execute(
                """
                SELECT id, analysed_at, activity_score, overall_stress
                FROM zone_runs
                WHERE zone_id = ? AND analysed_at >= ?
                ORDER BY analysed_at ASC
                LIMIT 1
                """,
                (zone_id, pivot),
            ).fetchone()

            result: dict[str, Any] = {
                "before": dict(before) if before else None,
                "after":  dict(after)  if after  else None,
            }
            if before and after:
                bs = before["activity_score"]
                as_ = after["activity_score"]
                if bs is not None and as_ is not None:
                    result["delta_activity_score"] = round(as_ - bs, 2)
            return result
    except Exception as exc:
        log.error("Failed to compute before/after for intervention %d: %s", intervention_id, exc)
        return None


# Initialise DB on import
init_db()
