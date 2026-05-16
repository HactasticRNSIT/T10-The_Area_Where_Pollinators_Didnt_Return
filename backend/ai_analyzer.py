"""
ai_analyzer.py
==============
Fix 3: Restructured Groq prompt for dramatically better AI quality +
       robust output validation with field-level checks and retry logic.
"""

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
# Fix 3: Restructured system prompt — clearer role, stricter output contract,
#        few-shot example guides response quality and length.
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are Dr. Ananya Krishnan, a senior agricultural ecologist at the National \
Centre for Integrated Pest Management with 20 years of field experience across \
Indian and tropical farming zones.

Your task is to read structured JSON data about a farm zone's pollinator \
ecosystem and return a JSON object with EXACTLY these two keys:

  "biodiversity_insight"
    • 2–3 plain-English sentences a farmer with no scientific background can act on.
    • Name the single most damaging factor first, explain what it is doing to the \
pollinators, and state the direct consequence for the harvest.
    • Avoid jargon. No abbreviations.
    • Target length: 60–90 words.

  "top_intervention"
    • One highly specific, immediately actionable recommendation.
    • Must include: WHAT to do, WHEN to do it (timing/season), HOW MUCH \
(quantities/concentrations where relevant), and WHICH species or products.
    • Max 60 words. Imperative mood. Start with a verb.

CONSTRAINTS:
- Output ONLY the JSON object. No markdown fences, no preamble, no trailing text.
- Both values must be non-empty strings.
- Do not hallucinate species or products not appropriate for the zone's geography.

EXAMPLE OUTPUT (for reference structure only — do not copy):
{
  "biodiversity_insight": "Neonicotinoid pesticides at 9 ppm are the primary \
threat here, impairing bee navigation so severely that fewer than half the \
expected pollinators are visiting flowers. This will cut mango fruit-set by an \
estimated 30–40% this season if left unaddressed.",
  "top_intervention": "Immediately replace neonicotinoid sprays with neem oil \
(Azadirachtin 1500 ppm, 3 mL/L water) and apply only after 6 PM during the \
next two flowering weeks to protect foraging bees."
}
"""


def _build_user_prompt(
    zone_id: str,
    lat: float,
    lon: float,
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
    raw: dict[str, Any],
) -> str:
    """
    Fix 3: More structured prompt layout — critical anomalies first, then
    supporting metrics grouped by theme. Reduces hallucination by giving the
    model the most decision-relevant facts at the top of its context window.
    """
    top_anomalies = anomalies[:5]
    critical = [a for a in top_anomalies if a["severity"] == "CRITICAL"]
    warnings  = [a for a in top_anomalies if a["severity"] == "WARNING"]

    payload = {
        "zone_id":     zone_id,
        "location":    {"lat": round(lat, 4), "lon": round(lon, 4)},
        "health_summary": {
            "activity_score":   scores["activity_score"],
            "activity_label":   scores["activity_label"],
            "stress_index":     scores["pollination_stress_index"],
            "crop_risk":        scores["crop_risk"],
        },
        "critical_anomalies": [
            {
                "factor":      a["factor"],
                "variable":    a["variable"],
                "observed":    a["observed_value"],
                "threshold":   a["threshold"],
                "description": a["description"][:140],
            }
            for a in critical
        ],
        "warning_anomalies": [
            {
                "factor":      a["factor"],
                "variable":    a["variable"],
                "observed":    a["observed_value"],
                "description": a["description"][:100],
            }
            for a in warnings
        ],
        "factor_stress_scores": scores["factor_scores"],
        "key_metrics": {
            "ndvi":               raw["ndvi"].get("ndvi"),
            "species_count":      raw["gbif"].get("species_count"),
            "soil_ph":            raw["soil"].get("ph"),
            "organic_carbon":     raw["soil"].get("organic_carbon_g_per_kg"),
            "drought_index":      raw["climate"].get("drought_index"),
            "pesticide_ppm":      raw["pesticide"].get("usage_ppm"),
            "pesticide_type":     raw["pesticide"].get("pesticide_type"),
            "root_zone_moisture": raw["nasa"].get("root_zone_wetness"),
            "visitation_ratio":   raw.get("visitation", {}).get("visitation_ratio"),
            "decline_rate_12w":   raw.get("visitation", {}).get("decline_rate_12w"),
            "timing_disruption":  raw.get("visitation", {}).get("pollination_timing_disruption"),
            "flowering_success":  raw.get("visitation", {}).get("flowering_success_rate"),
        },
    }
    return json.dumps(payload, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Fix 3: Robust output validation
# ──────────────────────────────────────────────────────────────────────────────

_MIN_INSIGHT_WORDS = 20
_MIN_INTERVENTION_WORDS = 8


def _validate_ai_response(data: dict) -> dict:
    """
    Fix 3: Validate the parsed LLM response.
    Raises ValueError with a descriptive message if any check fails so the
    caller can retry or fall back cleanly.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")

    missing = [k for k in ("biodiversity_insight", "top_intervention") if k not in data]
    if missing:
        raise ValueError(f"Missing required keys: {missing}")

    insight = data["biodiversity_insight"]
    intervention = data["top_intervention"]

    if not isinstance(insight, str) or not insight.strip():
        raise ValueError("biodiversity_insight is empty or not a string")
    if not isinstance(intervention, str) or not intervention.strip():
        raise ValueError("top_intervention is empty or not a string")

    if len(insight.split()) < _MIN_INSIGHT_WORDS:
        raise ValueError(
            f"biodiversity_insight too short ({len(insight.split())} words, "
            f"min {_MIN_INSIGHT_WORDS})"
        )
    if len(intervention.split()) < _MIN_INTERVENTION_WORDS:
        raise ValueError(
            f"top_intervention too short ({len(intervention.split())} words, "
            f"min {_MIN_INTERVENTION_WORDS})"
        )

    return {
        "biodiversity_insight": insight.strip(),
        "top_intervention":     intervention.strip(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Groq API caller — Fix 3: retry once on validation failure
# ──────────────────────────────────────────────────────────────────────────────

def _call_groq(user_content: str, attempt: int = 1) -> dict[str, str]:
    """
    Call Groq and return a validated response dict.
    Fix 3: retries once with temperature=0 if validation fails on attempt 1.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    temperature = GROQ_TEMPERATURE if attempt == 1 else 0.0

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       GROQ_MODEL,
        "temperature": temperature,
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
    raw_text = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip accidental markdown fences (Fix 3 robustness)
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    parsed = json.loads(raw_text)
    return _validate_ai_response(parsed)


# ──────────────────────────────────────────────────────────────────────────────
# Rule-based fallback (zero API cost)
# ──────────────────────────────────────────────────────────────────────────────

def _rule_based_fallback(
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
) -> dict[str, str]:
    label  = scores["activity_label"]
    stress = scores["pollination_stress_index"]
    top_a  = anomalies[0] if anomalies else None
    second = anomalies[1] if len(anomalies) > 1 else None

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
                "Addressing this issue promptly will be critical to maintaining "
                "sufficient pollinator activity for a productive harvest."
            )
    else:
        insight = (
            f"This farm zone currently shows a '{label}' pollinator status with "
            f"{stress.lower()} stress. No critical anomalies were detected, "
            "but ongoing monitoring is recommended to sustain ecosystem health."
        )

    top_intervention = (
        top_a["recommended_action"] if top_a else
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
    Attempt Groq LLM insights (with one retry on validation failure — Fix 3),
    then fall back to rule-based template.
    """
    user_content = _build_user_prompt(zone_id, lat, lon, scores, anomalies, raw)

    for attempt in (1, 2):
        try:
            result = _call_groq(user_content, attempt=attempt)
            result["insight_source"] = "groq"
            log.info("AI insights from Groq for zone %s (attempt %d)", zone_id, attempt)
            return result
        except Exception as exc:
            log.warning(
                "Groq attempt %d failed for zone %s (%s)%s",
                attempt, zone_id, exc,
                " — retrying with temperature=0" if attempt == 1 else " — using rule-based fallback",
            )

    fallback = _rule_based_fallback(scores, anomalies)
    fallback["insight_source"] = "rule_based_fallback"
    return fallback
