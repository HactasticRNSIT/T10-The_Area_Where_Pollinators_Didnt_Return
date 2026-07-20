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
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialise the interventions table (idempotent)."""
    with _get_connection(db_path) as conn:
        # WAL mode: set once here — persists on the file, not repeated per-connection.
        conn.execute("PRAGMA journal_mode=WAL;")
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


# ── Task 7: Efficacy summary ──────────────────────────────────────────────────
_EFFICACY_MIN_ROWS: int = 30  # data gate threshold


def get_total_intervention_count(db_path: str = DEFAULT_DB_PATH) -> int:
    """Return the total number of intervention records across all zones."""
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM interventions").fetchone()
            return row[0] if row else 0
    except Exception as exc:
        log.error("Failed to count interventions: %s", exc)
        return 0


def get_efficacy_summary(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    """
    Compute an aggregate efficacy summary across all recorded interventions.

    Data gate: returns ``{"data_sufficient": False, "total_records": N}`` when
    fewer than 30 matched before/after pairs exist.

    Returns
    -------
    dict with:
        data_sufficient        : bool
        total_records          : int   — all intervention rows in the DB
        paired_records         : int   — interventions with both before & after run
        mean_delta_activity    : float — average change in activity_score (paired only)
        pct_improved           : float — fraction of paired records that improved (%)
        per_intervention_type  : list[dict]  — breakdown by first word of intervention text
    """
    total = get_total_intervention_count(db_path)
    if total < _EFFICACY_MIN_ROWS:
        return {
            "data_sufficient": False,
            "total_records": total,
            "message": (
                f"Insufficient data: {total} intervention records found; "
                f"at least {_EFFICACY_MIN_ROWS} are needed for a statistically "
                f"meaningful efficacy estimate."
            ),
        }

    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT id, zone_id, intervention FROM interventions"
            ).fetchall()
    except Exception as exc:
        log.error("Efficacy query failed: %s", exc)
        return {"data_sufficient": False, "total_records": total, "error": str(exc)}

    deltas: list[float] = []
    type_buckets: dict[str, list[float]] = {}

    for row in rows:
        ba = get_before_after(row["zone_id"], row["id"], db_path=db_path)
        if not ba:
            continue
        delta = ba.get("delta_activity_score")
        if delta is None:
            continue
        deltas.append(delta)
        # Bucket by first word of intervention text as a rough category
        category = (row["intervention"] or "unknown").split()[0].lower()
        type_buckets.setdefault(category, []).append(delta)

    paired = len(deltas)
    if not paired:
        return {
            "data_sufficient": True,
            "total_records": total,
            "paired_records": 0,
            "mean_delta_activity": None,
            "pct_improved": None,
            "per_intervention_type": [],
            "message": "No paired before/after zone runs found yet.",
        }

    mean_delta = round(sum(deltas) / paired, 3)
    pct_improved = round(100.0 * sum(1 for d in deltas if d > 0) / paired, 1)

    per_type = [
        {
            "category": cat,
            "count": len(vals),
            "mean_delta": round(sum(vals) / len(vals), 3),
            "pct_improved": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1),
        }
        for cat, vals in sorted(type_buckets.items(), key=lambda x: -len(x[1]))
    ]

    return {
        "data_sufficient": True,
        "total_records": total,
        "paired_records": paired,
        "mean_delta_activity": mean_delta,
        "pct_improved": pct_improved,
        "per_intervention_type": per_type,
    }
