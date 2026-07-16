"""
ai_analyzer.py
==============
AI insights reoriented to actively INCREASE pollination rates and crop
fertility — not just identify threats. Every output key drives uplift.
"""

import json
import logging
import os
import textwrap
from typing import Any

__all__ = ["get_ai_insights"]

import requests

import time
import threading

from config import (
    API_ENDPOINTS,
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    REQUEST_TIMEOUT,
)

try:
    from metrics import polynexus_groq_calls, polynexus_groq_fallback
except ImportError:
    polynexus_groq_calls = None
    polynexus_groq_fallback = None

import re as _re

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Fix Vuln 3: Prompt-injection sanitizer
# Sensor-derived text (anomaly descriptions, field notes) is embedded in the
# LLM user message.  Strip patterns that look like instruction overrides so
# that a poisoned sensor value cannot hijack the advisory output.
# ──────────────────────────────────────────────────────────────────────────────

_INJECTION_PATTERNS = _re.compile(
    r"(ignore (all |previous )?instructions?|forget (your |all )?instructions?|"
    r"you are now|act as|jailbreak|system prompt|reveal (your |the )?prompt|"
    r"print (your |the )?instructions?|override (previous |all )?instructions?)",
    _re.IGNORECASE,
)
_MAX_FIELD_TEXT_LEN = 500  # truncate any single text field before embedding


def _sanitize_for_prompt(text: object) -> str:
    """Sanitise a single value before it is embedded in an LLM prompt.

    - Converts non-strings to their repr (safe).
    - Truncates to _MAX_FIELD_TEXT_LEN characters.
    - Replaces matched injection patterns with [REDACTED].
    """
    if not isinstance(text, str):
        return repr(text)
    text = text[:_MAX_FIELD_TEXT_LEN]
    text = _INJECTION_PATTERNS.sub("[REDACTED]", text)
    return text


# Circuit Breaker State
# Fix 1.5: protect with a Lock() so concurrent thread-pool calls cannot corrupt
# _cb_failures via a read-modify-write race (two threads both incrementing from 2
# would both trip the breaker with different _cb_open_until timestamps).
_cb_lock = threading.Lock()
_cb_failures = 0
_cb_open_until = 0.0
_CB_THRESHOLD = 3
_CB_COOLDOWN = 60.0

# ──────────────────────────────────────────────────────────────────────────────
# System prompt — every output key is oriented toward INCREASING pollination
# and crop fertility, not merely reducing harm.
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are Dr. Ananya Krishnan, a senior agricultural ecologist at the National \
Centre for Integrated Pest Management with 20 years of field experience across \
Indian and tropical farming zones.

Your PRIMARY GOAL is to help farmers INCREASE pollination rates and crop \
fertility — not just describe problems. Every insight must point toward \
concrete improvement in yield and flower fertilisation.

Your task is to read structured JSON data about a farm zone's pollinator \
ecosystem and return a JSON object with EXACTLY these THREE keys:

  "biodiversity_insight"
    • 2–3 plain-English sentences a farmer with no scientific background can act on.
    • Identify the biggest obstacle to pollination, explain how removing it will \
INCREASE pollinator visits and fruit/seed set, and state the expected fertility gain.
    • Frame positively: what the farmer GAINS by acting, not just what is lost.
    • Avoid jargon. No abbreviations. Target length: 60–90 words.

  "top_intervention"
    • One highly specific, immediately actionable step to BOOST pollination or \
soil fertility THIS season.
    • Must include: WHAT to do, WHEN to do it (timing/season), HOW MUCH \
(quantities/concentrations where relevant), and WHICH species or products.
    • Must end with an estimated benefit, e.g. "expected to increase fruit-set \
by 15–25%".
    • Max 70 words. Imperative mood. Start with a verb.

  "pollination_boost_actions"
    • A JSON array of exactly 3 short strings (max 20 words each).
    • Each string is one distinct, positive action to further increase \
pollination or soil fertility beyond the top intervention.
    • Actions must be season-aware and geography-appropriate.
    • Do NOT repeat the top_intervention.

CONSTRAINTS:
- Output ONLY the JSON object. No markdown fences, no preamble, no trailing text.
- All values must be non-empty. pollination_boost_actions must be an array of 3 strings.
- Do not hallucinate species or products not appropriate for the zone's geography.
- Every output must help the farmer INCREASE yield through better pollination.

EXAMPLE OUTPUT (for reference structure only — do not copy):
{
  "biodiversity_insight": "Reducing neonicotinoid sprays will allow native bees \
to return to your fields within 2–3 weeks, increasing flower visits by an \
estimated 40% and directly raising mango fruit-set this season.",
  "top_intervention": "Switch all pesticide applications to neem oil \
(Azadirachtin 1500 ppm, 3 mL/L water), applied after 6 PM only during the \
next two flowering weeks — expected to increase fruit-set by 20–35%.",
  "pollination_boost_actions": [
    "Plant 5-metre strips of phacelia or mustard on field borders to attract \
native solitary bees within 3 weeks.",
    "Install 10 simple bee hotels (bamboo bundles) per hectare on south-facing \
fences before next flowering flush.",
    "Apply compost tea (1:10 ratio) to soil around flowering plants to boost \
root-zone fertility and floral nectar quality."
  ]
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
    Structured prompt — critical anomalies first, then supporting metrics
    grouped by theme. Includes an explicit instruction to orient all outputs
    toward INCREASING pollination rates and crop fertility.
    """
    top_anomalies = anomalies[:5]
    critical = [a for a in top_anomalies if a["severity"] == "CRITICAL"]
    warnings  = [a for a in top_anomalies if a["severity"] == "WARNING"]

    payload = {
        "zone_id":     zone_id,
        "location":    {"lat": round(lat, 4), "lon": round(lon, 4)},
        "analysis_goal": (
            "Identify the highest-impact actions to INCREASE pollination rates "
            "and crop fertility in this zone. Prioritise positive gains, not just "
            "threat reduction."
        ),
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
                # Fix Vuln 3: sanitise description before embedding in prompt.
                "description": _sanitize_for_prompt(a["description"]),
                "uplift_opportunity": (
                    "Fixing this factor is expected to increase pollinator "
                    "visits and improve fruit/seed set."
                ),
            }
            for a in critical
        ],
        "warning_anomalies": [
            {
                "factor":      a["factor"],
                "variable":    a["variable"],
                "observed":    a["observed_value"],
                # Fix Vuln 3: sanitise description.
                "description": _sanitize_for_prompt(a["description"]),
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
        "source_caveats": {
            "visitation_source": raw.get("visitation", {}).get("source"),
            "visitation_is_modelled": raw.get("visitation", {}).get("source") == "modelled_visitation",
            "instruction": (
                "If visitation_is_modelled is true, describe visitation findings as modelled risk "
                "signals rather than direct field observations."
            ),
        },
    }
    return json.dumps(payload, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Robust output validation — includes the new pollination_boost_actions key
# ──────────────────────────────────────────────────────────────────────────────

_MIN_INSIGHT_WORDS = 20
_MIN_INTERVENTION_WORDS = 8
# Fix Vuln 3: cap LLM output length — prevents exfiltration attempts that return
# extremely long strings padded with hidden content.
_MAX_INSIGHT_CHARS = 1200
_MAX_INTERVENTION_CHARS = 600
_MAX_BOOST_ACTION_CHARS = 200


_BOOST_FALLBACKS = [
    "Plant flowering cover crops (e.g. sunflower or sesame) along field borders to attract foraging bees.",
    "Reduce pesticide frequency to at most once per fortnight and switch to evening-only applications.",
    "Add organic compost (2 t/ha) before the next sowing to improve soil fertility and nectar quality.",
]


def _validate_ai_response(data: dict) -> dict:
    """
    Validate the parsed LLM response. Raises ValueError if required keys are
    missing or values fail quality checks. Normalises pollination_boost_actions
    into a guaranteed list of 3 non-empty strings.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")

    required = ("biodiversity_insight", "top_intervention")
    missing = [k for k in required if k not in data]
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
    # Fix Vuln 3: hard cap on output length.
    if len(insight) > _MAX_INSIGHT_CHARS:
        raise ValueError(
            f"biodiversity_insight too long ({len(insight)} chars, max {_MAX_INSIGHT_CHARS})"
        )
    if len(intervention.split()) < _MIN_INTERVENTION_WORDS:
        raise ValueError(
            f"top_intervention too short ({len(intervention.split())} words, "
            f"min {_MIN_INTERVENTION_WORDS})"
        )
    if len(intervention) > _MAX_INTERVENTION_CHARS:
        raise ValueError(
            f"top_intervention too long ({len(intervention)} chars, max {_MAX_INTERVENTION_CHARS})"
        )

    # Normalise pollination_boost_actions — must be a list of 3 non-empty strings.
    raw_boost = data.get("pollination_boost_actions", [])
    if isinstance(raw_boost, list):
        boost = [str(item).strip() for item in raw_boost if str(item).strip()][:3]
    else:
        boost = []
    # Pad with fallbacks if the model returned fewer than 3
    while len(boost) < 3:
        boost.append(_BOOST_FALLBACKS[len(boost)])

    return {
        "biodiversity_insight":     insight.strip(),
        "top_intervention":         intervention.strip(),
        "pollination_boost_actions": boost,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Groq API caller — retries once with temperature=0 on validation failure
# ──────────────────────────────────────────────────────────────────────────────

def _call_groq(user_content: str, attempt: int = 1) -> dict[str, str]:
    """
    Call Groq and return a validated response dict.
    Retries once with temperature=0 if validation fails on attempt 1.
    """
    global _cb_failures, _cb_open_until

    # Fix 1.5: read circuit-breaker state under lock
    with _cb_lock:
        open_until = _cb_open_until
    if time.time() < open_until:
        raise RuntimeError("Groq circuit breaker is OPEN. Fast-failing.")

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
    
    if polynexus_groq_calls is not None:
        polynexus_groq_calls.inc()
        
    try:
        resp = requests.post(
            API_ENDPOINTS["groq"],
            headers=headers,
            json=body,
            timeout=10,  # 10s timeout to prevent hanging pipeline
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
        result = _validate_ai_response(parsed)
        # Fix 1.5: reset under lock
        with _cb_lock:
            _cb_failures = 0
        return result
    except Exception as exc:
        if attempt == 2:  # Only trip circuit breaker on final attempt failure
            # Fix 1.5: read-modify-write under lock to prevent race corruption
            with _cb_lock:
                _cb_failures += 1
                if _cb_failures >= _CB_THRESHOLD:
                    _cb_open_until = time.time() + _CB_COOLDOWN
                    log.error("Groq circuit breaker tripped. Opening for %d seconds", _CB_COOLDOWN)
        raise exc


# ──────────────────────────────────────────────────────────────────────────────
# Rule-based fallback (zero API cost)
# ──────────────────────────────────────────────────────────────────────────────

def _rule_based_fallback(
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
) -> dict[str, str]:
    """
    Rule-based fallback — frames outputs around increasing pollination and
    crop fertility, mirroring the AI system prompt's positive-action stance.
    """
    label  = scores["activity_label"]
    stress = str(scores.get("pollination_stress_index", "unknown"))
    top_a  = anomalies[0] if anomalies else None
    second = anomalies[1] if len(anomalies) > 1 else None

    if top_a:
        fst_factor = top_a["factor"].replace("_", " ")
        insight = (
            f"Correcting the {fst_factor} issue in this zone "
            f"(currently rated '{label}' with {stress.lower()} stress) "
            f"is the fastest route to increasing pollinator visits: "
            f"{top_a['description'][:150]}. "
        )
        if second:
            sec_factor = second["factor"].replace("_", " ")
            insight += (
                f"Addressing {sec_factor} next will further boost bee activity "
                "and improve fruit-set across your crop area."
            )
        else:
            insight += (
                "Acting promptly on this factor will help restore healthy "
                "pollinator populations and increase yield this season."
            )
    else:
        insight = (
            f"This farm zone shows a '{label}' pollinator status with "
            f"{stress.lower()} stress — a strong foundation for further "
            "increasing pollination rates. Focus on floral diversity and "
            "soil fertility improvements to push activity scores higher."
        )

    top_intervention = (
        top_a["recommended_action"] if top_a else
        "Plant flowering cover crops along 10% of field borders this season "
        "to attract native bees and increase pollination visits by an "
        "estimated 15–20%; monitor soil pH and organic matter quarterly."
    )

    # Fix 1.3: use set-based dedup with .strip() so that localized variants of
    # anomaly[0]'s action (which may equal anomaly[1]'s localized action) are
    # correctly excluded. Localization happens later so we dedup pre-localization here.
    seen_actions: set[str] = {top_intervention.strip()}
    boost_actions: list[str] = []
    for anomaly in anomalies[1:4]:
        action = (anomaly.get("recommended_action") or "").strip()
        if action and action not in seen_actions:
            boost_actions.append(action)
            seen_actions.add(action)
    while len(boost_actions) < 3:
        boost_actions.append(_BOOST_FALLBACKS[len(boost_actions)])

    return {
        "biodiversity_insight":      insight,
        "top_intervention":          top_intervention,
        "pollination_boost_actions": boost_actions[:3],
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
    Attempt Groq LLM insights (with one retry on validation failure),
    then fall back to rule-based template.
    All returned dicts include biodiversity_insight, top_intervention,
    and pollination_boost_actions — every field oriented toward increasing
    pollination rates and crop fertility.
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
    
    if polynexus_groq_fallback is not None:
        polynexus_groq_fallback.inc()
        
    return fallback
