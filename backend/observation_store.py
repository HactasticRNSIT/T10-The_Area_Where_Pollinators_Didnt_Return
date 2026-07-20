from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# Observations live in their own file, separate from zone_runs/interventions
# (polynexus_history.db). This prevents WAL auto-checkpoint stalls on the
# history write path from blocking pure SELECT reads on this store.
# Override with OBSERVATIONS_DB_PATH env var for custom deployments.
DEFAULT_DB_PATH = os.environ.get("OBSERVATIONS_DB_PATH", str(DATA_DIR / "polynexus_observations.db"))

# Guard: DDL runs exactly once per process per db path, never on the hot path.
_initialized: set[str] = set()


def _connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0)  # explicit timeout; WAL set once at init_db
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_initialized(db_path: str = DEFAULT_DB_PATH) -> None:
    """Run DDL at most once per process. Safe to call on write paths."""
    if db_path not in _initialized:
        init_db(db_path)
        _initialized.add(db_path)


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        # WAL mode: set once here — persists on the file, not repeated per-connection.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id         TEXT NOT NULL,
                observed_at     TEXT NOT NULL,
                species_name    TEXT,
                species_count   INTEGER,
                pollinator_count INTEGER,
                photo_filename  TEXT,
                notes           TEXT,
                outlier         INTEGER NOT NULL DEFAULT 0  -- 1 if value is >3x or <0.1x the zone reference
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_zone_time "
            "ON observations(zone_id, observed_at);"
        )
        # Migration: add outlier column if it was not present at table creation.
        # This is idempotent: adding an existing column raises an OperationalError
        # which we silently ignore.
        try:
            conn.execute("ALTER TABLE observations ADD COLUMN outlier INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # Column already exists


def record_observation(
    zone_id: str,
    species_name: str | None = None,
    species_count: int | None = None,
    pollinator_count: int | None = None,
    photo_filename: str | None = None,
    notes: str | None = None,
    observed_at: str | None = None,
    outlier: bool = False,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    _ensure_initialized(db_path)
    ts = observed_at or datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO observations (
                zone_id, observed_at, species_name, species_count,
                pollinator_count, photo_filename, notes, outlier
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (zone_id, ts, species_name, species_count, pollinator_count,
             photo_filename, notes, int(outlier)),
        )
        return int(cur.lastrowid)


def get_observations(
    zone_id: str,
    limit: int = 50,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    # Pure read path — do NOT call init_db/DDL here; _initialized ensures
    # the table exists from module import before any request arrives.
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM observations
            WHERE zone_id = ?
            ORDER BY observed_at DESC
            LIMIT ?
            """,
            (zone_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_visitation_override(
    zone_id: str,
    weeks: int = 12,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    observations = get_observations(zone_id, limit=500, db_path=db_path)
    if not observations:
        return None

    total_pollinators = sum(int(row.get("pollinator_count") or 0) for row in observations)
    species_names = {row.get("species_name") for row in observations if row.get("species_name")}
    species_total = sum(int(row.get("species_count") or 0) for row in observations)
    observed_species = max(len(species_names), species_total)

    if total_pollinators <= 0 and observed_species <= 0:
        return None

    sample_count = len(observations)
    avg_vph = round(max(total_pollinators, observed_species) / max(sample_count, 1), 2)
    expected = 12.6
    ratio = round(avg_vph / expected, 3) if expected else 0.0
    weekly = [avg_vph] * weeks
    return {
        "source": "field_observation_upload",
        "avg_visitations_per_hour": avg_vph,
        "expected_visitations_per_hour": expected,
        "visitation_ratio": ratio,
        "twelve_week_visits_per_hour": weekly,
        "decline_rate_12w": 0.0,
        "pollination_timing_disruption": max(0.0, 1.0 - ratio),
        "flowering_success_rate": min(1.0, ratio * 0.85),
        "recovery_volatility": 0.0,
        "total_observations": sample_count,
        "field_species_count": observed_species,
        "taxon_breakdown": {},
    }


# Initialise exactly once on module import — hot paths never call init_db again.
_ensure_initialized(DEFAULT_DB_PATH)
