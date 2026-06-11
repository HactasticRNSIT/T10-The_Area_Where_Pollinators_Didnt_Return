from __future__ import annotations

import textwrap
from typing import Any

from config import (
    RESILIENCE_SOC_OPTIMAL,
    RESILIENCE_SOC_MIN,
    get_species_norm_for_zone,
)
from hive_placement import get_hive_placement_advice

__all__ = ["build_decision_brief"]

FACTOR_LABELS = {
    "pesticide_exposure": "Pesticide pressure",
    "soil_fertility": "Soil fertility",
    "floral_diversity": "Floral diversity",
    "climate_variability": "Climate volatility",
    "nesting_availability": "Nesting habitat",
    "pollination_factor": "Pollination visits",
}

QUALITY_POINTS = {
    "live": 1.0,
    "modelled": 0.72,
    "fallback": 0.38,
}

SEVERITY_POINTS = {
    "CRITICAL": 1.0,
    "WARNING": 0.64,
    "INFO": 0.25,
}


def build_decision_brief(
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Create judge-friendly decision support from the same evidence used by scoring."""
    factor_scores = scores.get("factor_scores", {})
    weights = scores.get("factor_weights", {})
    overall_stress = float(scores.get("overall_stress", 0.0) or 0.0)
    source_health = raw.get("_realtime", {}).get("source_health", {})

    data_confidence = _data_confidence(source_health)
    top_drivers = _top_drivers(factor_scores, weights, source_health)
    intervention_plan = _intervention_plan(anomalies, factor_scores, weights)
    crop_exposure = _crop_exposure(scores.get("crop_dependency", {}), overall_stress)
    resilience_score = _resilience_score(scores, raw)
    caveats = _data_caveats(raw)
    hive_placement = get_hive_placement_advice(
        crops=scores.get("crop_dependency", {}),
        overall_stress=overall_stress,
    )
    margin = data_confidence["margin"]
    activity = float(scores.get("activity_score", 0.0) or 0.0)

    return {
        "decision_grade": _decision_grade(scores.get("activity_score", 0), data_confidence, anomalies),
        "data_confidence_score": data_confidence["score"],
        "data_confidence_label": data_confidence["label"],
        "source_scorecard": data_confidence["scorecard"],
        "resilience_score": resilience_score,
        "top_risk_drivers": top_drivers,
        "intervention_plan": intervention_plan,
        "crop_exposure": crop_exposure,
        "hive_placement": hive_placement,
        "data_caveats": caveats,
        "activity_score_margin": margin,
        "activity_score_range": [
            round(max(0.0, activity - margin), 1),
            round(min(100.0, activity + margin), 1),
        ],
        "judge_summary": _judge_summary(top_drivers, intervention_plan, data_confidence, resilience_score, caveats),
    }


def _data_confidence(source_health: dict[str, Any]) -> dict[str, Any]:
    if not source_health:
        return {"score": 50, "label": "Limited", "margin": 15, "scorecard": []}

    scorecard = []
    total = 0.0
    for key, item in sorted(source_health.items()):
        quality = item.get("quality", "fallback")
        points = QUALITY_POINTS.get(quality, 0.45)
        total += points
        scorecard.append({
            "signal": key,
            "source": item.get("source", "unknown"),
            "quality": quality,
            "score": round(points * 100),
        })

    score = round((total / max(len(source_health), 1)) * 100)
    if score >= 82:
        label = "High"
        margin = 3    # all-live sources: tight confidence interval
    elif score >= 62:
        label = "Medium"
        margin = 8    # mixed live/modelled: moderate uncertainty
    else:
        label = "Limited"
        margin = 15   # all-fallback: wide interval — data provenance uncertain
    return {"score": score, "label": label, "margin": margin, "scorecard": scorecard}


def _top_drivers(
    factor_scores: dict[str, Any],
    weights: dict[str, Any],
    source_health: dict[str, Any],
) -> list[dict[str, Any]]:
    source_map = {
        "pesticide_exposure": "pesticide",
        "soil_fertility": "soil",
        "floral_diversity": "ndvi",
        "climate_variability": "climate",
        "nesting_availability": "ndvi",
        "pollination_factor": "visitation",
    }
    rows = []
    for key, score in factor_scores.items():
        stress = float(score or 0.0)
        weight = float(weights.get(key, 0.0) or 0.0)
        source_key = source_map.get(key, key)
        quality = source_health.get(source_key, {}).get("quality", "modelled")
        rows.append({
            "factor": key,
            "label": FACTOR_LABELS.get(key, key.replace("_", " ").title()),
            "stress": round(stress, 2),
            "weight": round(weight, 2),
            "weighted_impact": round(stress * weight, 3),
            "evidence_quality": quality,
        })
    return sorted(rows, key=lambda row: row["weighted_impact"], reverse=True)[:4]


def _data_caveats(raw: dict[str, Any]) -> list[str]:
    caveats: list[str] = []
    if raw.get("visitation", {}).get("source") == "modelled_visitation":
        caveats.append(
            "Pollination visit metrics are modelled from proxy inputs, not direct field observations."
        )
    source_health = raw.get("_realtime", {}).get("source_health", {})
    fallback_signals = [
        signal for signal, item in source_health.items()
        if item.get("quality") == "fallback"
    ]
    if fallback_signals:
        caveats.append(
            "Fallback data used for: " + ", ".join(sorted(fallback_signals)) + "."
        )
    return caveats



# ──────────────────────────────────────────────────────────────────────────────
# Intervention cost-benefit model (roadmap item 3.1)
# ──────────────────────────────────────────────────────────────────────────────
# Each entry maps a keyword (matched case-insensitively in the action string)
# to a {cost_tier, uplift_range, timeframe} triple.
# Ordering: keywords are checked longest-first to prevent partial matches
# (e.g. "drip irrigation" matches before "irrigation").
# Sources:
#   - ICAR farm advisory bulletins for Indian cost benchmarks
#   - COLOSS BeeBook chapter 4 (colony management uplift estimates)
#   - FAO agri-environment scheme evaluation reports

_INTERVENTION_COST_MODEL: list[tuple[str, dict[str, str]]] = sorted([
    # Low-cost physical interventions
    ("bamboo-bundle bee hotel",   {"cost_tier": "Low",    "uplift_range": "5–15%",   "timeframe": "1 season"}),
    ("bee hotel",                  {"cost_tier": "Low",    "uplift_range": "5–15%",   "timeframe": "1 season"}),
    ("water station",              {"cost_tier": "Low",    "uplift_range": "5–10%",   "timeframe": "Immediate"}),
    ("shallow dishes",             {"cost_tier": "Low",    "uplift_range": "5–10%",   "timeframe": "Immediate"}),
    ("warning sign",               {"cost_tier": "Low",    "uplift_range": "5–10%",   "timeframe": "Immediate"}),
    ("notify",                     {"cost_tier": "Low",    "uplift_range": "5–10%",   "timeframe": "Immediate"}),
    ("mulch",                      {"cost_tier": "Low",    "uplift_range": "5–10%",   "timeframe": "1 season"}),
    ("compost tea",                {"cost_tier": "Low",    "uplift_range": "5–10%",   "timeframe": "1–2 seasons"}),
    ("delay mowing",               {"cost_tier": "Low",    "uplift_range": "5–10%",   "timeframe": "Immediate"}),
    # Moderate-cost agronomic / habitat
    ("flower strip",               {"cost_tier": "Low",    "uplift_range": "10–20%",  "timeframe": "1 season"}),
    ("wildflower strip",           {"cost_tier": "Low",    "uplift_range": "10–20%",  "timeframe": "1 season"}),
    ("cover crop",                 {"cost_tier": "Low",    "uplift_range": "10–20%",  "timeframe": "1 season"}),
    ("seed mix",                   {"cost_tier": "Low",    "uplift_range": "10–20%",  "timeframe": "1 season"}),
    ("windbreak net",              {"cost_tier": "Medium", "uplift_range": "10–20%",  "timeframe": "1 season"}),
    ("shade net",                  {"cost_tier": "Medium", "uplift_range": "10–20%",  "timeframe": "1 season"}),
    ("ipm",                        {"cost_tier": "Medium", "uplift_range": "20–40%",  "timeframe": "1–2 seasons"}),
    ("integrated pest management", {"cost_tier": "Medium", "uplift_range": "20–40%",  "timeframe": "1–2 seasons"}),
    ("biological control",         {"cost_tier": "Medium", "uplift_range": "10–25%",  "timeframe": "1–2 seasons"}),
    ("bio-pesticide",              {"cost_tier": "Medium", "uplift_range": "15–30%",  "timeframe": "1 season"}),
    ("neem oil",                   {"cost_tier": "Low",    "uplift_range": "15–25%",  "timeframe": "1 season"}),
    ("drip irrigation",            {"cost_tier": "Medium", "uplift_range": "10–20%",  "timeframe": "1 season"}),
    ("irrigation",                 {"cost_tier": "Medium", "uplift_range": "10–20%",  "timeframe": "1 season"}),
    ("agricultural lime",          {"cost_tier": "Low",    "uplift_range": "10–20%",  "timeframe": "1–2 seasons"}),
    ("lime",                       {"cost_tier": "Low",    "uplift_range": "10–20%",  "timeframe": "1–2 seasons"}),
    ("hedgerow",                   {"cost_tier": "Medium", "uplift_range": "15–30%",  "timeframe": "2–3 seasons"}),
    ("shrub belt",                 {"cost_tier": "Medium", "uplift_range": "15–25%",  "timeframe": "2–3 seasons"}),
    ("shelterbelt",                {"cost_tier": "Medium", "uplift_range": "10–20%",  "timeframe": "2–3 seasons"}),
    # Higher-cost structural
    ("relocate hive",              {"cost_tier": "Medium", "uplift_range": "20–40%",  "timeframe": "Immediate"}),
    ("managed hive",               {"cost_tier": "High",   "uplift_range": "30–60%",  "timeframe": "1 season"}),
    ("hive",                       {"cost_tier": "High",   "uplift_range": "30–60%",  "timeframe": "1 season"}),
    ("swale",                      {"cost_tier": "High",   "uplift_range": "10–20%",  "timeframe": "2–3 seasons"}),
    ("compost",                    {"cost_tier": "Medium", "uplift_range": "10–20%",  "timeframe": "1–2 seasons"}),
], key=lambda x: -len(x[0]))  # longest keyword first


def _cost_benefit(action: str) -> dict[str, str]:
    """
    Match the action text against _INTERVENTION_COST_MODEL keywords
    (case-insensitive, longest-first) and return {cost_tier, uplift_range, timeframe}.
    Falls back to a generic Medium estimate when no keyword matches.
    """
    action_lower = action.lower()
    for keyword, meta in _INTERVENTION_COST_MODEL:
        if keyword in action_lower:
            return meta
    return {"cost_tier": "Medium", "uplift_range": "10–20%", "timeframe": "1–2 seasons"}


def _intervention_plan(
    anomalies: list[dict[str, Any]],
    factor_scores: dict[str, Any],
    weights: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Build a prioritised action plan where each item is explicitly framed as
    an opportunity to INCREASE pollination or soil fertility, not merely
    reduce a threat.
    """
    plan = []
    seen = set()
    for anomaly in anomalies:
        factor = anomaly.get("factor", "")
        variable = anomaly.get("variable", "")
        key = (factor, variable)
        if key in seen:
            continue
        seen.add(key)
        severity = anomaly.get("severity", "INFO")
        factor_stress = float(factor_scores.get(factor, 0.0) or 0.0)
        factor_weight = float(weights.get(factor, 0.0) or 0.0)
        priority = (
            SEVERITY_POINTS.get(severity, 0.25) * 56
            + factor_stress * 28
            + factor_weight * 16
        )
        action = anomaly.get("recommended_action", "")
        # textwrap.shorten avoids mid-word cuts that degrade LLM prompt quality (#20)
        description = textwrap.shorten(
            anomaly.get("description", ""), width=140, placeholder="…"
        )
        cost_meta = _cost_benefit(action)
        plan.append({
            "priority_score": round(priority),
            "severity": severity,
            "factor": factor,
            "label": FACTOR_LABELS.get(factor, factor.replace("_", " ").title()),
            "variable": variable,
            "action": action,
            "pollination_uplift": _pollination_uplift_phrase(factor, severity),
            "why": description,
            "cost_tier":   cost_meta["cost_tier"],
            "uplift_range": cost_meta["uplift_range"],
            "timeframe":   cost_meta["timeframe"],
        })
    return sorted(plan, key=lambda row: row["priority_score"], reverse=True)[:5]


_UPLIFT_PHRASES: dict[str, str] = {
    "pesticide_exposure":   "Reducing pesticide pressure can increase bee visits by 30–50%.",
    "soil_fertility":       "Improving soil fertility boosts floral nectar quality and pollinator foraging.",
    "floral_diversity":     "Adding flowering species directly increases the number of pollinator visits.",
    "climate_variability":  "Buffering climate stress extends the active pollination window.",
    "nesting_availability": "Creating nesting sites grows resident pollinator populations season-on-season.",
    "pollination_factor":   "Restoring visit rates is the most direct path to higher fruit and seed set.",
}


def _pollination_uplift_phrase(factor: str, severity: str) -> str:
    base = _UPLIFT_PHRASES.get(factor, "Addressing this factor will improve pollinator activity.")
    if severity == "CRITICAL":
        return f"Priority: {base}"
    return base


def _crop_exposure(crop_dependency: dict[str, Any], overall_stress: float) -> list[dict[str, Any]]:
    rows = []
    for crop, dependency in crop_dependency.items():
        dep = float(dependency or 0.0)
        exposure = dep * overall_stress
        if exposure >= 0.45:
            level = "High"
        elif exposure >= 0.22:
            level = "Moderate"
        else:
            level = "Low"
        rows.append({
            "crop": crop,
            "dependency": round(dep, 2),
            "exposure_score": round(exposure, 2),
            "level": level,
        })
    return sorted(rows, key=lambda row: row["exposure_score"], reverse=True)[:5]


def _resilience_score(scores: dict[str, Any], raw: dict[str, Any]) -> int:
    """
    Ecosystem resilience score (0–100).

    Combines five independent axes — each weighted to reflect how much it
    contributes to long-term recovery capacity, not just current performance:

    Axis                Weight  Rationale
    ──────────────────  ──────  ────────────────────────────────────────────
    Activity (health)    0.30   Current ecosystem function
    Habitat quality      0.25   Structural capacity to sustain pollinators
    Biodiversity (GBIF)  0.20   Species richness as buffering capacity
    Soil carbon          0.15   Long-term soil health and recovery potential
    Visit stability      0.10   Trend direction from 12-week decline rate

    Data confidence from the decision engine is applied as a discount:
    a fully-fallback run can at most score 75% of the calculated value,
    preventing false confidence when all data is synthetic.
    """
    activity  = float(scores.get("activity_score", 0.0) or 0.0) / 100.0
    habitat   = float(scores.get("habitat_suitability_score", 0.0) or 0.0) / 100.0

    # Biodiversity richness: zone-aware species norm so tropical high-biodiversity
    # zones (e.g. Kerala, IN_KL) don't saturate at maximum benefit too easily.
    zone_id = raw.get("_meta", {}).get("zone_id", "")
    species_count = float(raw.get("gbif", {}).get("species_count", 0) or 0)
    resilience_norm = get_species_norm_for_zone(zone_id, norm_key="resilience")
    biodiversity  = min(1.0, species_count / resilience_norm)

    # Soil organic carbon
    soc = float(raw.get("soil", {}).get("organic_carbon_g_per_kg", 1.5) or 1.5)
    soil_health = _clamp_01((soc - RESILIENCE_SOC_MIN) / (RESILIENCE_SOC_OPTIMAL - RESILIENCE_SOC_MIN))

    # Visit stability: no decline → 1.0; 50 %+ decline over 12 weeks → 0.0
    decline = float(raw.get("visitation", {}).get("decline_rate_12w", 0.0) or 0.0)
    visit_stability = max(0.0, 1.0 - min(decline, 1.0) * 2.0)

    raw_score = (
        activity        * 0.30 +
        habitat         * 0.25 +
        biodiversity    * 0.20 +
        soil_health     * 0.15 +
        visit_stability * 0.10
    )

    # Data-quality discount: 100% live data → no discount; all fallback → cap at 75%.
    source_health = raw.get("_realtime", {}).get("source_health", {})
    if source_health:
        live_ratio = sum(
            1 for item in source_health.values() if item.get("quality") == "live"
        ) / len(source_health)
        # Discount range: live_ratio=1 → factor 1.0; live_ratio=0 → factor 0.75
        confidence_factor = 0.75 + 0.25 * live_ratio
    else:
        confidence_factor = 0.85  # unknown provenance: modest discount

    return round(max(0.0, min(1.0, raw_score * confidence_factor)) * 100)


def _clamp_01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _decision_grade(activity_score: Any, data_confidence: dict[str, Any], anomalies: list[dict[str, Any]]) -> str:
    activity = float(activity_score or 0.0)
    confidence = float(data_confidence.get("score", 50) or 50)
    critical_count = sum(1 for item in anomalies if item.get("severity") == "CRITICAL")
    blended = activity * 0.58 + confidence * 0.32 - critical_count * 8
    if blended >= 78:
        return "A"
    if blended >= 64:
        return "B"
    if blended >= 50:
        return "C"
    if blended >= 36:
        return "D"
    return "E"


def _judge_summary(
    drivers: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    confidence: dict[str, Any],
    resilience_score: int,
    caveats: list[str] | None = None,
) -> str:
    """
    Produce a judge summary oriented toward INCREASING pollination and crop
    fertility, not just naming the top risk driver.
    """
    top_driver   = drivers[0]["label"] if drivers else "Ecosystem stress"
    top_action   = plan[0]["label"] if plan else "Monitoring"
    uplift_hint  = plan[0].get("pollination_uplift", "") if plan else ""

    # Lowercase only the FIRST character so compound noun phrases like
    # "Nesting habitat" or "Pollination visits" remain readable in running prose
    # rather than being fully downcased to "nesting habitat" everywhere. (#21)
    action_text = top_action[0].lower() + top_action[1:] if top_action else ""
    driver_text = top_driver[0].lower() + top_driver[1:] if top_driver else ""

    summary = (
        f"To increase pollination rates in this zone, the highest-priority step is "
        f"to address {action_text} — the leading source of stress is "
        f"{driver_text}. "
        f"Decision confidence is {confidence['label'].lower()} at {confidence['score']}%, "
        f"with an ecosystem resilience score of {resilience_score}%."
    )
    if uplift_hint:
        summary += f" {uplift_hint}"
    if caveats:
        summary += f" Note: {caveats[0]}"
    return summary
