"""
geo_classifier.py
=================
Agro-climatic zone resolution with three-tier crop lookup:

  Tier 1 — Static state registry  (Nominatim reverse geocoding → crop_registry.py)
            Deterministic, no API key, ICAR/Ministry of Agriculture sourced.
            Cached for 30 days at 0.1° precision (~11 km grid cell).

  Tier 2 — Groq LLM enrichment    (optional, env-flag controlled)
            Falls back to this ONLY when the state is not in the registry
            (e.g. non-Indian coordinates, or a newly added state).
            Cached for 7 days; disabled via GROQ_CROP_LOOKUP_ENABLED=0.

  Tier 3 — Climate-zone heuristic  (always available, no network call)
            Rule-based fallback using elevation / temperature / precipitation.
"""

import logging
import os
import json
import time
import requests
import threading

from config import (
    API_ENDPOINTS,
    GROQ_CROP_CACHE_PRECISION,
    GROQ_CROP_CACHE_TTL_SECONDS,
    GROQ_CROP_LOOKUP_ENABLED,
    GROQ_CROP_LOOKUP_TIMEOUT,
    GROQ_MODEL,
    REQUEST_TIMEOUT,
)
from crop_registry import get_crops_for_state
from network import make_session

_SESSION = make_session()

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Shared TTL-cache helper
# ──────────────────────────────────────────────────────────────────────────────

_GEOCODE_TTL = 30 * 24 * 3600   # 30 days — state names change very rarely

__all__ = ["resolve_agro_zone", "clear_crop_cache"]

# key → (expiry_monotonic, value)
_crop_cache: dict[tuple[float, float], tuple[float, dict | None]] = {}
_geocode_cache: dict[tuple[float, float], tuple[float, str | None]] = {}
_crop_cache_lock = threading.Lock()
_geocode_cache_lock = threading.Lock()


def _round_key(lat: float, lon: float) -> tuple[float, float]:
    """Round to GROQ_CROP_CACHE_PRECISION decimal places (~11 km at prec=1)."""
    p = GROQ_CROP_CACHE_PRECISION
    return (round(lat, p), round(lon, p))


def clear_crop_cache() -> None:
    """Test helper and operational escape hatch for refreshed crop lookups."""
    with _crop_cache_lock:
        _crop_cache.clear()
    with _geocode_cache_lock:
        _geocode_cache.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Tier 1a — Nominatim reverse geocoding
# ──────────────────────────────────────────────────────────────────────────────

def _reverse_geocode_state(lat: float, lon: float) -> str | None:
    """
    Call Nominatim to resolve (lat, lon) to an Indian state name.
    Returns the state string (title-cased as Nominatim delivers it) or None.

    Caches result for 30 days at 0.1° precision.
    Fails silently — a None return lets the pipeline fall through to Tier 2.
    """
    key = _round_key(lat, lon)
    now = time.monotonic()
    with _geocode_cache_lock:
        cached = _geocode_cache.get(key)
        if cached and now < cached[0]:
            return cached[1]

    def _remember(val: str | None) -> str | None:
        with _geocode_cache_lock:
            _geocode_cache[key] = (now + _GEOCODE_TTL, val)
        log.debug("[geocode_cache] cold-cache populated for %s -> %s", key, val)
        return val

    try:
        resp = _SESSION.get(
            API_ENDPOINTS["nominatim_reverse"],
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 5},
            headers={"User-Agent": "PolyNexus/1.0 pollinator-ecosystem-dashboard"},
            timeout=min(REQUEST_TIMEOUT, 6),
        )
        resp.raise_for_status()
        address = resp.json().get("address", {})
        state = address.get("state") or address.get("state_district")
        if state:
            log.info("[geocode] (%.4f, %.4f) → state: %s", lat, lon, state)
            return _remember(state)
        log.info("[geocode] No state in Nominatim response for (%.4f, %.4f)", lat, lon)
        return _remember(None)
    except Exception as exc:
        log.warning("[geocode] Nominatim failed for (%.4f, %.4f): %s", lat, lon, exc)
        return _remember(None)


# ──────────────────────────────────────────────────────────────────────────────
# Tier 1b — Static state registry lookup
# ──────────────────────────────────────────────────────────────────────────────

def _lookup_state_crops(lat: float, lon: float) -> dict | None:
    """
    Resolve state via Nominatim then look up the static ICAR crop registry.
    Returns a crop→dependency dict or None if the state is not registered.
    """
    state_name = _reverse_geocode_state(lat, lon)
    if not state_name:
        return None
    crops = get_crops_for_state(state_name)
    if crops:
        log.info("[crop_registry] Found %d crops for state '%s'", len(crops), state_name)
    else:
        log.info("[crop_registry] State '%s' not in registry — will try LLM", state_name)
    return crops


# ──────────────────────────────────────────────────────────────────────────────
# Tier 2 — Groq LLM enrichment (optional)
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_groq_crops(lat: float, lon: float) -> dict | None:
    """
    Ask the Groq LLM for the top-5 crops at (lat, lon) with pollination
    dependency factors.  Result is cached for GROQ_CROP_CACHE_TTL_SECONDS.
    Returns None on any failure so the caller falls through to Tier 3.
    """
    cache_key = _round_key(lat, lon)
    now = time.monotonic()
    with _crop_cache_lock:
        cached = _crop_cache.get(cache_key)
        if cached and now < cached[0]:
            return cached[1]

    def remember(value: dict | None) -> dict | None:
        with _crop_cache_lock:
            _crop_cache[cache_key] = (now + GROQ_CROP_CACHE_TTL_SECONDS, value)
        log.debug("[crop_cache] cold-cache populated for %s -> %s", cache_key, list(value.keys()) if value else None)
        return value

    if not GROQ_CROP_LOOKUP_ENABLED:
        log.info("Groq crop lookup disabled; using rule-based crop fallback.")
        return remember(None)

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        log.warning("No GROQ_API_KEY found, cannot dynamically fetch crops.")
        return remember(None)

    prompt = (
        f"You are an agricultural data API. Given the coordinates lat: {lat:.4f}, lon: {lon:.4f}, "
        "return a JSON object containing the top 5 major agricultural crops grown in this region "
        "and their estimated pollination dependency factor (0.0 to 1.0). "
        "Output ONLY valid JSON like: {\"crops\": {\"crop_name\": 0.5}}."
    )

    body = {
        "model": GROQ_MODEL,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }

    try:
        r = _SESSION.post(
            API_ENDPOINTS.get("groq", "https://api.groq.com/openai/v1/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=min(REQUEST_TIMEOUT, GROQ_CROP_LOOKUP_TIMEOUT)
        )
        r.raise_for_status()
        raw_text = r.json()["choices"][0]["message"]["content"].strip()
        parsed = json.loads(raw_text)
        if "crops" in parsed and isinstance(parsed["crops"], dict):
            normalized_crops = {k.lower(): float(v) for k, v in parsed["crops"].items()}
            log.info("[groq_crops] Resolved %d crops for (%.4f, %.4f)", len(normalized_crops), lat, lon)
            return remember(normalized_crops)
    except Exception as e:
        log.warning(f"Groq API crop resolution failed for {lat}, {lon}: {e}")

    return remember(None)


# ──────────────────────────────────────────────────────────────────────────────
# Public: resolve_agro_zone
# ──────────────────────────────────────────────────────────────────────────────

def resolve_agro_zone(lat: float, lon: float, climate_data: dict) -> dict:
    """
    Dynamically resolve agro-climatic zone using lat/lon and climate signals.

    Crop resolution order (first hit wins):
      1. Static state registry  (Nominatim geocode → crop_registry.INDIA_STATE_CROP_REGISTRY)
      2. Groq LLM enrichment    (if enabled and state not in registry)
      3. Climate-zone heuristic (always available, no network call)

    Returns a geo_profile dict containing:
      classification, crops, crop_source, factor_weights, elevation,
      inferred_annual_precip_mm, mean_temp_c
    """
    # ── 1. Extract climate signals ────────────────────────────────────────────
    elevation = climate_data.get("elevation") or 0
    temp = climate_data.get("temp_mean_c")
    if temp is None:
        temp = 25.0
    precip_daily = climate_data.get("avg_daily_precip_mm")
    if precip_daily is None:
        precip_daily = 0.0
    precip = precip_daily * 365.0  # annualise daily mean

    if "total_precipitation_mm" in climate_data and climate_data.get("days_fetched", 0) > 0:
        total_p = climate_data.get("total_precipitation_mm")
        days = climate_data.get("days_fetched", 0)
        if total_p is not None and days > 0:
            precip = (total_p / days) * 365.0

    # ── 2. Climate-zone classification + fallback crops ───────────────────────
    if elevation > 1500:
        classification = "High Altitude Temperate"
        fallback_crops = {"apple": 0.95, "cherry": 0.90, "walnut": 0.85, "wheat": 0.10, "barley": 0.05}
        weights = {
            "climate_variability": 0.20, "floral_diversity": 0.20,
            "pesticide_exposure": 0.15, "soil_fertility": 0.20,
            "nesting_availability": 0.15, "pollination_factor": 0.10
        }
    elif precip < 400:
        classification = "Arid / Semi-Arid"
        fallback_crops = {"mustard": 0.80, "bajra": 0.35, "wheat": 0.10, "cotton": 0.15, "cumin": 0.65}
        weights = {
            "climate_variability": 0.30, "soil_fertility": 0.15,
            "floral_diversity": 0.15, "pesticide_exposure": 0.20,
            "nesting_availability": 0.10, "pollination_factor": 0.10
        }
    elif precip > 2000:
        classification = "Tropical Wet"
        fallback_crops = {"tea": 0.70, "rubber": 0.05, "coconut": 0.30, "rice": 0.03, "black pepper": 0.60}
        weights = {
            "pesticide_exposure": 0.25, "soil_fertility": 0.20,
            "floral_diversity": 0.25, "climate_variability": 0.10,
            "nesting_availability": 0.10, "pollination_factor": 0.10
        }
    elif temp > 25 and precip > 800:
        classification = "Tropical Monsoon / Savannah"
        fallback_crops = {"mango": 0.75, "cotton": 0.15, "rice": 0.03, "groundnut": 0.30, "pulses": 0.40}
        weights = {
            "pesticide_exposure": 0.35, "soil_fertility": 0.20,
            "floral_diversity": 0.15, "climate_variability": 0.15,
            "nesting_availability": 0.05, "pollination_factor": 0.10
        }
    else:
        classification = "Sub-Tropical / Temperate"
        fallback_crops = {"wheat": 0.10, "mustard": 0.80, "soybean": 0.25, "sunflower": 0.65, "maize": 0.05}
        weights = {
            "pesticide_exposure": 0.30, "soil_fertility": 0.25,
            "floral_diversity": 0.15, "climate_variability": 0.15,
            "nesting_availability": 0.05, "pollination_factor": 0.10
        }

    # ── 3. Crop resolution: state registry → LLM → climate fallback ──────────
    crops = _lookup_state_crops(lat, lon)
    crop_source = "state_registry"

    if crops is None:
        crops = _fetch_groq_crops(lat, lon)
        crop_source = "groq_llm"

    if crops is None:
        crops = fallback_crops
        crop_source = "climate_zone_fallback"
        log.info("[geo_classifier] Using climate-zone fallback crops for (%.2f, %.2f)", lat, lon)

    log.info(
        "[geo_classifier] (%.2f, %.2f) → %s | crop_source=%s | crops=%s",
        lat, lon, classification, crop_source, list(crops.keys())
    )

    return {
        "classification":          classification,
        "crops":                   crops,
        "crop_source":             crop_source,
        "factor_weights":          weights,
        "elevation":               elevation,
        "inferred_annual_precip_mm": round(precip, 1),
        "mean_temp_c":             round(temp, 1),
    }
