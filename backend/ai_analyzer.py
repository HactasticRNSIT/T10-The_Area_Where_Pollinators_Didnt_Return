

import json
import logging
import os
from typing import Any

import requests

from config import (
    API_ENDPOINTS,
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    REQUEST_TIMEOUT,
)

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert agricultural ecologist specialising in pollinator health.
You receive structured JSON data about a farm zone's pollinator ecosystem and
return ONLY a valid JSON object with exactly two keys:

  "biodiversity_insight": A 2–3 sentence plain-English explanation that a
    farmer with no scientific background can understand. Explain what is
    happening to the pollinators and why it matters for their harvest.
    Be specific about which factors are most problematic.

  "top_intervention": A single, highly specific, immediately actionable
    recommendation that will have the greatest impact on recovering pollinator
    health in this zone. Include timing, quantities, and species where relevant.

Do NOT include any text outside the JSON object. Do NOT add markdown fences.
"""

def _build_user_prompt(
    zone_id: str,
    lat: float,
    lon: float,
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
    raw: dict[str, Any],
) -> str:
    """Construct a compact, token-efficient prompt for the LLM."""

    # Select the top 5 anomalies to keep the prompt concise
    top_anomalies = anomalies[:5]

    payload = {
        "zone_id":        zone_id,
        "coordinates":    {"lat": lat, "lon": lon},
        "activity_score": scores["activity_score"],
        "activity_label": scores["activity_label"],
        "stress_index":   scores["pollination_stress_index"],
        "factor_scores":  scores["factor_scores"],
        "top_anomalies": [
            {
                "factor":      a["factor"],
                "severity":    a["severity"],
                "variable":    a["variable"],
                "observed":    a["observed_value"],
                "description": a["description"][:120],  # trim for token budget
            }
            for a in top_anomalies
        ],
        "crop_risk":      scores["crop_risk"],
        "key_metrics": {
            "ndvi":                raw["ndvi"].get("ndvi"),
            "species_count":       raw["gbif"].get("species_count"),
            "soil_ph":             raw["soil"].get("ph"),
            "organic_carbon":      raw["soil"].get("organic_carbon_g_per_kg"),
            "drought_index":       raw["climate"].get("drought_index"),
            "pesticide_ppm":       raw["pesticide"].get("usage_ppm"),
            "pesticide_type":      raw["pesticide"].get("pesticide_type"),
            "root_zone_moisture":  raw["nasa"].get("root_zone_wetness"),
            "visitation_ratio":    raw.get("visitation", {}).get("visitation_ratio"),
            "decline_rate_12w":    raw.get("visitation", {}).get("decline_rate_12w"),
            "timing_disruption":   raw.get("visitation", {}).get("pollination_timing_disruption"),
            "flowering_success":   raw.get("visitation", {}).get("flowering_success_rate"),
        },
    }
    return json.dumps(payload, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# API caller
# ──────────────────────────────────────────────────────────────────────────────

def _call_groq(user_content: str) -> dict[str, str]:
    """
    Send a request to the Groq chat completion endpoint.

    Returns parsed dict with 'biodiversity_insight' and 'top_intervention'.
    Raises on HTTP or JSON errors (caller handles fallback).
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       GROQ_MODEL,
        "temperature": GROQ_TEMPERATURE,
        "max_tokens":  GROQ_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(
        API_ENDPOINTS["groq"],
        headers=headers,
        json=body,
        timeout=REQUEST_TIMEOUT * 2,
    )
    resp.raise_for_status()
    data = resp.json()
    raw_text = data["choices"][0]["message"]["content"].strip()
    return json.loads(raw_text)


# ──────────────────────────────────────────────────────────────────────────────
# Fallback generator (rule-based, zero API cost)
# ──────────────────────────────────────────────────────────────────────────────

def _rule_based_fallback(
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
) -> dict[str, str]:
    """
    Generate template-based insight and intervention without any API call.
    Used when Groq is unavailable or GROQ_API_KEY is not set.
    """
    label  = scores["activity_label"]
    stress = scores["pollination_stress_index"]
    top_a  = anomalies[0] if anomalies else None
    second = anomalies[1] if len(anomalies) > 1 else None

    # Biodiversity insight
    if top_a:
        fst_factor = top_a["factor"].replace("_", " ")
        fst_sev    = top_a["severity"].lower()
        insight = (
            f"This farm zone is currently rated '{label}' with a {stress.lower()} "
            f"pollination stress level. The most serious issue is a {fst_sev} problem "
            f"with {fst_factor}: {top_a['description'][:150]}. "
        )
        if second:
            sec_factor = second["factor"].replace("_", " ")
            insight += (
                f"A secondary concern is {sec_factor}, which is also reducing the ability "
                f"of bees and other pollinators to thrive in this area."
            )
        else:
            insight += (
                f"Addressing this issue promptly will be critical to maintaining "
                f"sufficient pollinator activity for a productive harvest."
            )
    else:
        insight = (
            f"This farm zone currently shows a '{label}' pollinator status with "
            f"{stress.lower()} stress. No critical anomalies were detected, "
            f"but ongoing monitoring is recommended to sustain ecosystem health."
        )

    # Top intervention: use the highest-priority anomaly's recommended_action
    if top_a:
        top_intervention = top_a["recommended_action"]
    else:
        top_intervention = (
            "Maintain current biodiversity-friendly practices; continue monitoring "
            "soil pH and organic matter quarterly to sustain healthy pollinator habitat."
        )

    return {
        "biodiversity_insight": insight,
        "top_intervention":     top_intervention,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def get_ai_insights(
    zone_id: str,
    lat: float,
    lon: float,
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
    raw: dict[str, Any],
) -> dict[str, str]:
    """
    Attempt to get LLM-generated insights from Groq; fall back to
    rule-based template on any failure.

    Returns
    -------
    {
        "biodiversity_insight": str,
        "top_intervention":     str,
        "insight_source":       "groq" | "rule_based_fallback",
    }
    """
    try:
        user_content = _build_user_prompt(zone_id, lat, lon, scores, anomalies, raw)
        result = _call_groq(user_content)

        # Validate expected keys
        if "biodiversity_insight" not in result or "top_intervention" not in result:
            raise ValueError("LLM response missing required keys.")

        result["insight_source"] = "groq"
        log.info("AI insights received from Groq for zone %s", zone_id)
        return result

    except Exception as exc:
        log.warning(
            "Groq AI call failed for zone %s (%s) – using rule-based fallback",
            zone_id, exc,
        )
        fallback = _rule_based_fallback(scores, anomalies)
        fallback["insight_source"] = "rule_based_fallback"
        return fallback
