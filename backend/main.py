import argparse
import asyncio
import json
import logging
import sys
import time
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

# Ensure backend directory is in sys.path so sibling modules can be imported
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from ai_analyzer import get_ai_insights
from anomaly_detector import detect_anomalies, has_ai_trigger_anomaly
from data_fetcher import fetch_all
from decision_engine import build_decision_brief
from scorer import apply_anomaly_pressure, compute_all_scores
from geo_classifier import resolve_agro_zone


def _run_scoring(
    raw: dict[str, Any],
    zone_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], int, int]:
    """CPU-bound scoring + anomaly detection. Runs in asyncio.to_thread so the
    event loop is not blocked and can continue accepting / dispatching requests.
    Returns (scores, anomalies, scorer_ms, anomaly_ms)."""
    _t_score0 = time.monotonic()
    scores = compute_all_scores(raw, zone_id=zone_id)
    scorer_ms = round((time.monotonic() - _t_score0) * 1000)

    _t_anom0 = time.monotonic()
    anomalies = detect_anomalies(raw, zone_id=zone_id)
    scores = apply_anomaly_pressure(
        scores,
        anomalies,
        zone_id=zone_id,
        geo_profile=raw.get("_meta", {}).get("geo_profile"),
    )
    anomaly_ms = round((time.monotonic() - _t_anom0) * 1000)
    return scores, anomalies, scorer_ms, anomaly_ms

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
    if visitation.get("source") in ("modelled_visitation", "open_meteo_derived_visitation"):
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

    try:
        from phenology import CROP_FLOWERING_WINDOWS
        geo_profile = raw.get("_meta", {}).get("geo_profile", {})
        primary_crop = geo_profile.get("primary_crop")
        if primary_crop and primary_crop not in CROP_FLOWERING_WINDOWS:
            caveats.append(f"No flowering window data available for {primary_crop}. Phenology-based anomaly escalation is disabled for this zone.")
    except Exception:
        pass

    return caveats


# ──────────────────────────────────────────────────────────────────────────────
# Core pipeline
# ──────────────────────────────────────────────────────────────────────────────

async def analyse_zone(
    zone_id: str,
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """
    Orchestrate the 5-factor pollinator ecosystem analysis.

    Parameters
    ----------
    zone_id : str   Unique identifier for the location
    lat     : float Latitude in decimal degrees
    lon     : float Longitude in decimal degrees

    Returns
    -------
    dict  Fully structured JSON-serialisable output
    """
    # ── 1. Data Fetching ────────────────────────────────────────────────────
    _t0 = time.monotonic()
    # ── Task 8: Load Testing Mock Hook ────────────────────────────────────────
    import os as _os
    if _os.environ.get("POLYNEXUS_MOCK_EXTERNAL", "0") == "1":
        log.warning("⚠️ MOCK MODE ACTIVE ⚠️ — POLYNEXUS_MOCK_EXTERNAL=1 is set. No real data will be fetched!")
        from mock_data import get_full_mock_bundle
        # In mock mode, skip resolve_agro_zone entirely (it would hit Nominatim/Groq).
        # get_full_mock_bundle already embeds a usable geo_profile in _meta.
        raw = get_full_mock_bundle(lat, lon)
        raw["_meta"]["zone_id"] = zone_id
        geo_profile = raw["_meta"]["geo_profile"]
    else:
        # 1. Fetch live data concurrently
        from data_fetcher import fetch_open_meteo, fetch_all
        climate_data = await asyncio.to_thread(fetch_open_meteo, lat, lon)
        geo_profile = resolve_agro_zone(lat, lon, climate_data)
        raw = await asyncio.to_thread(fetch_all, lat, lon, zone_id=zone_id, geo_profile=geo_profile)

    # Inject zone metadata so scorer sub-functions can read lat + zone_id
    # without changing every function signature in the hot path.
    raw["_meta"] = {"lat": lat, "lon": lon, "zone_id": zone_id, "geo_profile": geo_profile}

    # ── 2+3. Scoring + Anomaly Detection (in thread — never blocks event loop) ───
    # These are CPU-bound steps (~20-50ms each) with no I/O. Running them on
    # asyncio.to_thread means concurrent requests are processed in parallel by
    # the thread pool rather than queuing behind each other on the event loop.
    scores, anomalies, _scorer_ms, _anomaly_ms = await asyncio.to_thread(
        _run_scoring, raw, zone_id
    )
    log.info("[timing] scorer zone=%s scorer_ms=%d anomaly_ms=%d", zone_id, _scorer_ms, _anomaly_ms)
    groq_called = has_ai_trigger_anomaly(anomalies)
    if groq_called:
        ai_result = await asyncio.to_thread(get_ai_insights, zone_id, lat, lon, scores, anomalies, raw)
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

    # ── 6. Structured audit log (4.3) ────────────────────────────────────────
    # Emitted at INFO level so it is silent in default WARNING mode but
    # captured when the caller sets LOG_LEVEL=INFO or STRUCTURED_LOG=true.
    # The `audit` extra key lets the JsonFormatter in api.py serialize this
    # as a flat machine-readable JSON line for log aggregators (e.g. Loki).
    _duration_ms = round((time.monotonic() - _t0) * 1000)
    _data_quality = output.get("_meta", {}).get("data_quality", {})
    log.info(
        "analyse_zone completed zone=%s lat=%.4f lon=%.4f duration_ms=%d score=%d",
        zone_id, lat, lon, _duration_ms, output.get("activity_score", 0),
        extra={
            "audit": {
                "zone_id":       zone_id,
                "lat":           lat,
                "lon":           lon,
                "duration_ms":   _duration_ms,
                "activity_score": output.get("activity_score"),
                "overall_stress": round(scores.get("overall_stress", 0.0), 4),
                "anomaly_count":  len(anomalies),
                "critical_count": sum(1 for a in anomalies if a["severity"] == "CRITICAL"),
                "warning_count":  sum(1 for a in anomalies if a["severity"] == "WARNING"),
                "groq_called":    groq_called,
                "insight_source": ai_result.get("insight_source"),
                "data_quality":   _data_quality,
                "decision_grade": decision_brief.get("decision_grade"),
            }
        },
    )

    try:
        from metrics import polynexus_source_health
        for source_name, quality in _data_quality.items():
            if source_name in ("climate", "nasa", "gbif", "soil", "ndvi", "pesticide", "visitation"):
                polynexus_source_health.labels(source_name=source_name).set(1.0 if quality == "live" else 0.0)
    except Exception as exc:
        log.warning("Failed to record source health metrics: %s", exc)

    # ── 7. Non-blocking history write ─────────────────────────────────────────
    # save_run is fire-and-forget: the client does not consume this data in the
    # current response, so we never block on it. asyncio.create_task schedules
    # the write on the event loop and returns immediately; the task runs after
    # the response is sent. Errors are logged but do not affect the caller.
    async def _bg_save_run(zid: str, out: dict) -> None:
        try:
            from history_store import save_run
            await asyncio.to_thread(save_run, zid, out)
        except Exception as _exc:
            log.error("Background save_run failed zone=%s: %s", zid, _exc)

    asyncio.create_task(_bg_save_run(zone_id, output))

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
        "activity_score": round(scores["activity_score"], 2),
        "activity_score_margin": decision_brief.get("activity_score_margin"),
        "activity_score_range": decision_brief.get("activity_score_range"),
        "activity_label": scores["activity_label"],

        # ── Per-factor breakdown (stress 0–1) ──────────────────────────────────
        # Round at the serialisation boundary so internal computations retain
        # full float precision throughout the pipeline (change #4).
        "contribution_scores": {k: round(v, 2) for k, v in scores["contribution_scores"].items()},

        # ── Explainability: ranked stress drivers ─────────────────────────────
        # Sorted descending by raw stress so the frontend can render a
        # "why this score" panel without recomputing anything client-side.
        # interaction_penalty is a meta-value, not a named factor — excluded.
        "top_stress_factors": [
            {"factor": k.replace("_", " ").title(), "stress": round(v, 2)}
            for k, v in sorted(
                (
                    (k, v) for k, v in scores["factor_scores"].items()
                    if k != "interaction_penalty"
                ),
                key=lambda kv: kv[1],
                reverse=True,
            )
        ],

        # ── Habitat ───────────────────────────────────────────────────────────
        "habitat_suitability_score": scores["habitat_suitability_score"],

        # ── Stress index ──────────────────────────────────────────────────────
        "pollination_stress_index": scores["pollination_stress_index"],

        # ── Anomalies (sorted CRITICAL first) ─────────────────────────────
        "anomalies": anomalies,

        # ── Crop risk ─────────────────────────────────────────────────────
        "crop_risk": scores["crop_risk"],
        "crop_risk_details": scores.get("crop_risk_details", {}),
        "crop_dependency": {k: round(v, 2) for k, v in scores.get("crop_dependency", {}).items()},
        "phenology_calendar": __import__("phenology")._get_windows_for_crops(list(scores.get("crop_dependency", {}).keys()), zone_id),
        "crop_weighted_stress": (
            round(scores["crop_weighted_stress"], 4)
            if scores.get("crop_weighted_stress") is not None else None
        ),

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
            "visitation_summary": raw.get("visitation", {}),
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
    result = asyncio.run(analyse_zone(
        zone_id=args.zone_id,
        lat=args.lat,
        lon=args.lon,
    ))
    indent = 2 if args.pretty else None
    sys.stdout.write(json.dumps(result, indent=indent, ensure_ascii=False))
    sys.stdout.write("\n")
