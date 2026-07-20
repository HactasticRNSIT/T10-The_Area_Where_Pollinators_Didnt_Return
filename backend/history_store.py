import sqlite3
import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Default DB path handling
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = os.environ.get("HISTORY_DB_PATH", str(DATA_DIR / "polynexus_history.db"))

# When False (default), save_run stores only the summary scalar columns and skips
# json.dumps(result) — which is a GIL-holding operation on the large result dict.
# Set POLYNEXUS_HISTORY_RAW=1 in the environment to enable full blob storage
# (useful for diagnostics, never needed in normal production).
_STORE_RAW_JSON: bool = os.environ.get("POLYNEXUS_HISTORY_RAW", "0") == "1"

# Guard: DDL runs exactly once per process per db path, never on the hot path.
_initialized: set[str] = set()


def _get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Returns a SQLite connection. WAL mode is set once at init_db time."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_initialized(db_path: str = DEFAULT_DB_PATH) -> None:
    """Call init_db at most once per process. Safe to call on every request."""
    if db_path not in _initialized:
        run_migrations(db_path)
        _initialized.add(db_path)

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialise the history store schema."""
    with _get_connection(db_path) as conn:
        # WAL mode: set once here — persists on the file, not repeated per-connection.
        conn.execute("PRAGMA journal_mode=WAL;")
        # Raise checkpoint threshold from 1000 pages (default ~4MB) to 10000 pages
        # (~40MB) so WAL auto-checkpoints — which briefly serialize all new connections —
        # happen far less frequently under concurrent write load.
        conn.execute("PRAGMA wal_autocheckpoint=10000;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS zone_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id      TEXT NOT NULL,
                analysed_at  TEXT NOT NULL,
                activity_score     REAL,
                resilience_score   INTEGER,
                overall_stress     REAL,
                anomaly_count      INTEGER,
                critical_count     INTEGER,
                data_quality_score INTEGER,
                visitation_source  TEXT,
                raw_json     TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_zone_time ON zone_runs(zone_id, analysed_at);")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)

def run_migrations(db_path: str = DEFAULT_DB_PATH) -> None:
    """Run lightweight schema migrations idempotently."""
    init_db(db_path)
    with _get_connection(db_path) as conn:
        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        current_version = row["v"] if row["v"] is not None else 0

        # Migration 1: example base version setup
        if current_version < 1:
            conn.execute("INSERT INTO schema_version (version) VALUES (1)")
            conn.commit()
            current_version = 1
        
        # Add future migrations here, e.g.
        # if current_version < 2:
        #     conn.execute("ALTER TABLE zone_runs ADD COLUMN new_column TEXT")
        #     conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        #     conn.commit()
        #     current_version = 2

def save_run(zone_id: str, result: dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> None:
    """Save an analysis result to the history store."""
    try:
        _ensure_initialized(db_path)
        now_utc = datetime.now(timezone.utc).isoformat()
        
        # Extract metadata from result
        activity_score = result.get("activity_score")
        resilience_score = result.get("resilience_score")
        overall_stress = result.get("overall_stress")
        
        # Count anomalies
        anomalies = result.get("anomalies", [])
        anomaly_count = len(anomalies)
        critical_count = sum(1 for a in anomalies if a.get("severity") == "CRITICAL")
        
        # Extract quality info
        meta = result.get("_meta", {})
        data_quality_score = meta.get("data_quality_score")
        
        visitation_source = None
        if "visitation" in result:
            visitation_source = result["visitation"].get("source")
            
        # Serialise the full result only when explicitly requested.
        # json.dumps(result) on the large analysis output dict is a GIL-holding
        # operation (~30-80ms) that blocks the event loop while running in a
        # background thread; skip it by default.
        raw_json = json.dumps(result) if _STORE_RAW_JSON else None
        
        with _get_connection(db_path) as conn:
            conn.execute("""
                INSERT INTO zone_runs (
                    zone_id, analysed_at, activity_score, resilience_score, 
                    overall_stress, anomaly_count, critical_count, 
                    data_quality_score, visitation_source, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                zone_id, now_utc, activity_score, resilience_score,
                overall_stress, anomaly_count, critical_count,
                data_quality_score, visitation_source, raw_json
            ))
    except Exception as exc:
        log.error("Failed to save history run for zone %s: %s", zone_id, exc)

def get_history(zone_id: str, limit: int = 52, db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """Retrieve history for a zone, ordered by newest first."""
    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute("""
                SELECT * FROM zone_runs 
                WHERE zone_id = ? 
                ORDER BY analysed_at DESC 
                LIMIT ?
            """, (zone_id, limit)).fetchall()
            
            history = []
            for row in rows:
                item = dict(row)
                if item["raw_json"]:
                    try:
                        item["raw_data"] = json.loads(item["raw_json"])
                    except Exception:
                        item["raw_data"] = None
                del item["raw_json"]
                history.append(item)
            return history
    except Exception as exc:
        log.error("Failed to fetch history for zone %s: %s", zone_id, exc)
        return []

def get_trend(zone_id: str, weeks: int = 12, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Calculate trend in activity score over the specified number of weeks."""
    history = get_history(zone_id, limit=weeks, db_path=db_path)
    
    if not history or len(history) < 2:
        return {"direction": "stable", "delta": 0.0, "samples": len(history)}
        
    latest_score = history[0].get("activity_score", 0.0)
    oldest_score = history[-1].get("activity_score", 0.0)
    
    # Check if either score is None
    if latest_score is None or oldest_score is None:
        return {"direction": "unknown", "delta": 0.0, "samples": len(history)}
        
    delta = latest_score - oldest_score
    
    if delta > 2.0:
        direction = "improving"
    elif delta < -2.0:
        direction = "declining"
    else:
        direction = "stable"
        
    return {
        "direction": direction,
        "delta": round(delta, 2),
        "samples": len(history),
        "latest_score": latest_score,
        "oldest_score": oldest_score,
        "time_span_days": (datetime.fromisoformat(history[0]["analysed_at"]) - 
                           datetime.fromisoformat(history[-1]["analysed_at"])).days
    }


def get_seasonal_threshold_overrides(
    zone_id: str,
    month: int | None = None,
    min_samples: int = 3,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """
    Derive conservative threshold overrides from same-month zone history.

    Current history rows persist run summaries rather than every raw sensor
    reading, so this uses stored activity/overall stress as a seasonal baseline
    and only adjusts broad stress-related thresholds. When future rows include
    raw NDVI or climate observations, this function can extend the same overlay
    without changing config.get_anomaly_thresholds_for_zone.
    """
    target_month = month or datetime.now(timezone.utc).month
    history = get_history(zone_id, limit=156, db_path=db_path)
    same_month = []
    seen_dates = set()
    for item in history:
        try:
            analysed_at = datetime.fromisoformat(item["analysed_at"])
        except Exception:
            continue
        date_str = analysed_at.date().isoformat()
        if analysed_at.month == target_month and date_str not in seen_dates:
            same_month.append(item)
            seen_dates.add(date_str)

    if len(same_month) < min_samples:
        return {}

    # Require samples to span at least 14 days
    if len(same_month) >= 2:
        dates = [datetime.fromisoformat(item["analysed_at"]).date() for item in same_month]
        spread = (max(dates) - min(dates)).days
        if spread < 14:
            return {}  # Fall back to global defaults if spread is < 14 days

    scores = [
        float(item["activity_score"])
        for item in same_month
        if item.get("activity_score") is not None
    ]
    stresses = [
        float(item["overall_stress"])
        for item in same_month
        if item.get("overall_stress") is not None
    ]
    if not scores or not stresses:
        return {}

    avg_score = sum(scores) / len(scores)
    avg_stress = sum(stresses) / len(stresses)
    overrides: dict[str, Any] = {
        "seasonal_baseline_samples": len(same_month),
        "seasonal_activity_baseline": round(avg_score, 2),
    }

    if avg_score >= 72:
        overrides["visitation_ratio_warning"] = 0.82
    elif avg_score <= 45 or avg_stress >= 0.55:
        overrides["visitation_ratio_warning"] = 0.68

    return overrides

# Run migrations exactly once on import (populates _initialized for the default path).
run_migrations()
_initialized.add(DEFAULT_DB_PATH)
