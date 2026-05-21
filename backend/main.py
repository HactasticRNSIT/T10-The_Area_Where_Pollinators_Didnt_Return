

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs) -> None:
        return None

# Load environment variables (e.g., GROQ_API_KEY from .env) when python-dotenv is installed.
load_dotenv(Path(__file__).parent / ".env")

from ai_analyzer import get_ai_insights
from anomaly_detector import detect_anomalies, has_ai_trigger_anomaly
from data_fetcher import fetch_all
from decision_engine import build_decision_brief
from scorer import apply_anomaly_pressure, compute_all_scores
from geo_classifier import resolve_agro_zone

# Suppress all library-level logging so stdout stays clean JSON
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


def _quality_from_source(source: str) -> str:
    source = (source or "unknown").lower()
    if (
        "mock" in source
        or "unavailable" in source
        or source in {"inat_no_data", "unknown"}
    ):
        return "fallback"
    if "modelled" in source or source.startswith("owid_fao_"):
        return "modelled"
    return "live"


def _build_data_caveats(raw: dict[str, Any]) -> list[str]:
    caveats: list[str] = []
    visitation = raw.get("visitation", {})
    if visitation.get("source") == "modelled_visitation":
        caveats.append(
            "Pollination visitation metrics are synthetic model outputs derived from habitat, "
            "pesticide, climate, and biodiversity proxies because no live visitation observations "
            "were available for this zone. Treat visitation anomalies as modelled risk signals, "
            "not field observations."
        )
    for signal in ("climate", "nasa", "gbif", "soil", "ndvi", "pesticide"):
        warning = raw.get(signal, {}).get("_data_warning")
        if warning:
            caveats.append(f"{signal}: {warning}")
    return caveats


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
    raw = fetch_all(lat, lon, zone_id=zone_id)

    # Inject zone metadata so scorer sub-functions can read lat + zone_id
    # without changing every function signature in the hot path.
    raw["_meta"] = {"lat": lat, "lon": lon, "zone_id": zone_id, "geo_profile": resolve_agro_zone(lat, lon, raw.get("climate", {}))}

    # ── 2. Scoring ──────────────────────────────────────────────────────────
    scores = compute_all_scores(raw, zone_id=zone_id)

    # ── 3. Anomaly Detection ─────────────────────────────────────────────────
    anomalies = detect_anomalies(raw, zone_id=zone_id)
    scores = apply_anomaly_pressure(
        scores,
        anomalies,
        zone_id=zone_id,
        geo_profile=raw.get("_meta", {}).get("geo_profile"),
    )

    # ── 4. AI Insights (conditional) ─────────────────────────────────────────
    if has_ai_trigger_anomaly(anomalies):
        ai_result = get_ai_insights(zone_id, lat, lon, scores, anomalies, raw)
    else:
        # Healthy zone – skip AI call; still provide positive pollination boost guidance
        ai_result = {
            "biodiversity_insight": (
                f"Zone {zone_id} is in healthy ecological condition — a great starting point "
                f"for increasing pollination further. Pollinator activity is strong and no "
                f"significant stress factors were detected. Small habitat improvements can push "
                f"visit rates and fruit-set even higher this season."
            ),
            "top_intervention": (
                "Add 5-metre flowering border strips of phacelia or marigold along at least "
                "two field edges to attract additional native bees and increase pollination "
                "visit frequency by an estimated 10–20% — low cost, high reward."
            ),
            "pollination_boost_actions": [
                "Install simple bamboo-bundle bee hotels (10 per hectare) on south-facing "
                "fences to grow resident solitary bee populations before next flowering season.",
                "Apply compost tea (1:10 dilution) around flowering plants monthly to enrich "
                "soil fertility and improve floral nectar quality for pollinators.",
                "Conduct a quarterly pollinator species survey to track diversity trends and "
                "catch any early biodiversity changes before they reduce visit rates.",
            ],
            "insight_source": "healthy_zone_no_ai",
        }

    # ── 5. Assemble output ───────────────────────────────────────────────────
    decision_brief = build_decision_brief(scores, anomalies, raw)
    output = _build_output(zone_id, lat, lon, scores, anomalies, ai_result, raw, decision_brief)
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
    ai_result: dict[str, Any],
    raw: dict[str, Any],
    decision_brief: dict[str, Any],
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
    data_quality = {key: _quality_from_source(source) for key, source in data_sources.items()}
    data_caveats = _build_data_caveats(raw)

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
        "biodiversity_insight":     ai_result["biodiversity_insight"],
        "top_intervention":         ai_result["top_intervention"],
        "pollination_boost_actions": ai_result.get("pollination_boost_actions", []),
        "decision_brief":           decision_brief,

        # ── Metadata / audit ─────────────────────────────────────────────
        "_meta": {
            "insight_source":   ai_result.get("insight_source"),
            "anomaly_count":    len(anomalies),
            "critical_count":   sum(1 for a in anomalies if a["severity"] == "CRITICAL"),
            "warning_count":    sum(1 for a in anomalies if a["severity"] == "WARNING"),
            "data_sources":     data_sources,
            "data_quality":      data_quality,
            "data_caveats":      data_caveats,
            "realtime_status":   raw.get("_realtime", {}),
            "visitation_summary": {
                "twelve_week_visits_per_hour": raw.get("visitation", {}).get("twelve_week_visits_per_hour"),
            },
            "raw_factor_stress": scores["factor_scores"],
            "factor_weights":    scores.get("factor_weights"),
            "overall_stress":    scores["overall_stress"],
            "anomaly_pressure_adjustment": scores.get("anomaly_pressure_adjustment"),
            "crop_dependency_basis": scores.get("crop_dependency_basis"),
            "crop_source":      raw.get("_meta", {}).get("geo_profile", {}).get("crop_source"),
            "geo_classification": raw.get("_meta", {}).get("geo_profile", {}).get("classification"),
            "model_limitations": (
                "Factor scores are decision-support estimates from available climate, land-cover, species, "
                "pesticide, modelled, and fallback inputs. Modelled visitation signals are proxy estimates "
                "unless the visitation source is a live observation provider. Do not read these outputs as "
                "calibrated farm-level sensor measurements or universally validated causal percentages."
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
