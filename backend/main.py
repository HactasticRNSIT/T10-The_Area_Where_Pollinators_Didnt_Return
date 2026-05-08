

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

# Load environment variables (e.g., GROQ_API_KEY from .env)
load_dotenv()

from ai_analyzer import get_ai_insights
from anomaly_detector import detect_anomalies, has_ai_trigger_anomaly
from data_fetcher import fetch_all
from scorer import compute_all_scores

# Suppress all library-level logging so stdout stays clean JSON
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Core pipeline
# ──────────────────────────────────────────────────────────────────────────────

def analyse_zone(
    zone_id: str,
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """
    Run the full analysis pipeline for a single farm zone.

    Pipeline:
        1. Fetch raw data (Open-Meteo, NASA POWER, GBIF, mocks)
        2. Compute factor scores and activity score
        3. Detect anomalies (rule-based, Layer 1)
        4. Conditionally call AI for insights (Layer 2, only if anomalies exist)
        5. Assemble final dashboard-ready JSON

    Parameters
    ----------
    zone_id : str   Unique identifier for the farm zone
    lat     : float Latitude in decimal degrees
    lon     : float Longitude in decimal degrees

    Returns
    -------
    dict  Fully structured JSON-serialisable output
    """
    # ── 1. Data Fetching ────────────────────────────────────────────────────
    raw = fetch_all(lat, lon)

    # Inject zone metadata so scorer sub-functions can read lat + zone_id
    # without changing every function signature in the hot path.
    raw["_meta"] = {"lat": lat, "lon": lon, "zone_id": zone_id}

    # ── 2. Scoring ──────────────────────────────────────────────────────────
    scores = compute_all_scores(raw, zone_id=zone_id)

    # ── 3. Anomaly Detection ─────────────────────────────────────────────────
    anomalies = detect_anomalies(raw, zone_id=zone_id)

    # ── 4. AI Insights (conditional) ─────────────────────────────────────────
    if has_ai_trigger_anomaly(anomalies):
        ai_result = get_ai_insights(zone_id, lat, lon, scores, anomalies, raw)
    else:
        # Healthy zone – skip AI call entirely
        ai_result = {
            "biodiversity_insight": (
                f"Zone {zone_id} is in healthy ecological condition. "
                f"Pollinator activity is strong with no significant stress factors detected. "
                f"Continuing current land management practices will sustain this outcome."
            ),
            "top_intervention": (
                "Maintain existing habitat management; conduct a quarterly species survey "
                "to detect any early-stage biodiversity changes before they become critical."
            ),
            "insight_source": "healthy_zone_no_ai",
        }

    # ── 5. Assemble output ───────────────────────────────────────────────────
    output = _build_output(zone_id, lat, lon, scores, anomalies, ai_result, raw)
    return output


# ──────────────────────────────────────────────────────────────────────────────
# Output builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_output(
    zone_id: str,
    lat: float,
    lon: float,
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
    ai_result: dict[str, str],
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the final dashboard-ready JSON structure."""

    # Data source provenance
    data_sources = {
        "climate":   raw["climate"].get("source", "unknown"),
        "nasa":      raw["nasa"].get("source", "unknown"),
        "gbif":      raw["gbif"].get("source", "unknown"),
        "soil":      raw["soil"].get("source", "unknown"),
        "ndvi":      raw["ndvi"].get("source", "unknown"),
        "pesticide": raw["pesticide"].get("source", "unknown"),
        "visitation": raw.get("visitation", {}).get("source", "unknown"),
    }
    data_quality = {
        key: ("modelled" if source in ("modelled_visitation",) else "mock" if "mock" in source else "live")
        for key, source in data_sources.items()
    }

    return {
        # ── Identity ──────────────────────────────────────────────────────
        "zone_id":    zone_id,
        "latitude":   lat,
        "longitude":  lon,
        "analysed_at": datetime.now(timezone.utc).isoformat(),

        # ── Primary health score ──────────────────────────────────────────
        "activity_score": scores["activity_score"],
        "activity_label": scores["activity_label"],

        # ── Per-factor breakdown (stress 0–1) ──────────────────────────────
        "contribution_scores": scores["contribution_scores"],

        # ── Habitat ───────────────────────────────────────────────────────
        "habitat_suitability_score": scores["habitat_suitability_score"],

        # ── Stress index ──────────────────────────────────────────────────
        "pollination_stress_index": scores["pollination_stress_index"],

        # ── Anomalies (sorted CRITICAL first) ─────────────────────────────
        "anomalies": anomalies,

        # ── Crop risk ─────────────────────────────────────────────────────
        "crop_risk": scores["crop_risk"],
        "crop_dependency": scores["crop_dependency"],

        # ── AI / rule-based insights ──────────────────────────────────────
        "biodiversity_insight": ai_result["biodiversity_insight"],
        "top_intervention":     ai_result["top_intervention"],

        # ── Metadata / audit ─────────────────────────────────────────────
        "_meta": {
            "insight_source":   ai_result.get("insight_source"),
            "anomaly_count":    len(anomalies),
            "critical_count":   sum(1 for a in anomalies if a["severity"] == "CRITICAL"),
            "warning_count":    sum(1 for a in anomalies if a["severity"] == "WARNING"),
            "data_sources":     data_sources,
            "data_quality":      data_quality,
            "visitation_summary": {
                "avg_visitations_per_hour": raw.get("visitation", {}).get("avg_visitations_per_hour"),
                "expected_visitations_per_hour": raw.get("visitation", {}).get("expected_visitations_per_hour"),
                "visitation_ratio": raw.get("visitation", {}).get("visitation_ratio"),
                "decline_rate_12w": raw.get("visitation", {}).get("decline_rate_12w"),
                "pollination_timing_disruption": raw.get("visitation", {}).get("pollination_timing_disruption"),
                "flowering_success_rate": raw.get("visitation", {}).get("flowering_success_rate"),
                "twelve_week_visits_per_hour": raw.get("visitation", {}).get("twelve_week_visits_per_hour"),
            },
            "raw_factor_stress": scores["factor_scores"],
            "factor_weights":    scores.get("factor_weights"),
            "overall_stress":    scores["overall_stress"],
            "crop_dependency_basis": scores.get("crop_dependency_basis"),
            "model_limitations": (
                "Factor scores are modelled decision-support estimates from available climate, land-cover, "
                "species, pesticide, and mock/surrogate inputs. They should not be read as calibrated farm-level "
                "sensor measurements or universally validated causal percentages."
            ),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pollinator Ecosystem Analysis Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--zone_id", required=True, help="Unique zone identifier")
    parser.add_argument("--lat",     required=True, type=float, help="Latitude (decimal degrees)")
    parser.add_argument("--lon",     required=True, type=float, help="Longitude (decimal degrees)")
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=False,
        help="Pretty-print the JSON output (indent=2)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = analyse_zone(
        zone_id=args.zone_id,
        lat=args.lat,
        lon=args.lon,
    )
    indent = 2 if args.pretty else None
    sys.stdout.write(json.dumps(result, indent=indent, ensure_ascii=False))
    sys.stdout.write("\n")
