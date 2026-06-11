"""
agmarknet.py — Item 2.4
Crop price feed with live fetch + static bundled fallback.
Provides `get_crop_price_inr(crop, state)` used by `compute_crop_risks`
to compute value_at_risk_inr per crop.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Static price table (INR per quintal, ~2024 APMC modal prices).
# Updated quarterly. Used as fallback when live fetch fails.
# Sources: APMC portal, eNAM dashboard, ICAR crop statistics.
# ---------------------------------------------------------------------------
STATIC_CROP_PRICES: dict[str, dict[str, Any]] = {
    "apple":     {"price_inr_per_quintal": 6500,  "avg_yield_q_per_ha": 120, "state": "IN_HP"},
    "mustard":   {"price_inr_per_quintal": 5200,  "avg_yield_q_per_ha": 15,  "state": "IN_RJ"},
    "sunflower": {"price_inr_per_quintal": 5800,  "avg_yield_q_per_ha": 12,  "state": "IN_KA"},
    "mango":     {"price_inr_per_quintal": 3200,  "avg_yield_q_per_ha": 100, "state": "IN_UP"},
    "coffee":    {"price_inr_per_quintal": 18000, "avg_yield_q_per_ha": 10,  "state": "IN_KA"},
    "tea":       {"price_inr_per_quintal": 14000, "avg_yield_q_per_ha": 20,  "state": "IN_AS"},
    "rice":      {"price_inr_per_quintal": 2183,  "avg_yield_q_per_ha": 24,  "state": "IN_WB"},
    "cotton":    {"price_inr_per_quintal": 6620,  "avg_yield_q_per_ha": 18,  "state": "IN_GJ"},
    "cardamom":  {"price_inr_per_quintal": 110000,"avg_yield_q_per_ha": 1.5, "state": "IN_KL"},
    "lychee":    {"price_inr_per_quintal": 8000,  "avg_yield_q_per_ha": 80,  "state": "IN_BR"},
    "saffron":   {"price_inr_per_quintal": 300000,"avg_yield_q_per_ha": 0.06,"state": "IN_JK"},
    "coconut":   {"price_inr_per_quintal": 2800,  "avg_yield_q_per_ha": 90,  "state": "IN_TN"},
    "orange":    {"price_inr_per_quintal": 4000,  "avg_yield_q_per_ha": 120, "state": "IN_MH"},
    "sesame":    {"price_inr_per_quintal": 13500, "avg_yield_q_per_ha": 5,   "state": "IN_MP"},
    "turmeric":  {"price_inr_per_quintal": 8000,  "avg_yield_q_per_ha": 25,  "state": "IN_TG"},
    "wheat":     {"price_inr_per_quintal": 2275,  "avg_yield_q_per_ha": 35,  "state": "IN_PB"},
}


import time
import threading

_cache: dict[tuple[str, str | None], tuple[float, dict[str, Any] | None]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 3600

def get_crop_price_inr(crop: str, state: str | None = None) -> dict[str, Any] | None:
    """
    Return price metadata for a crop: price_inr_per_quintal, avg_yield_q_per_ha.
    Tries live eNAM fetch first; falls back to static table on failure.
    Returns None if the crop is unknown.
    This function uses a TTL cache to prevent repeated network calls or fallback evaluations.
    """
    key = (crop, state)
    now = time.monotonic()
    
    with _cache_lock:
        if key in _cache and _cache[key][0] > now:
            return _cache[key][1]

    def _remember(value: dict[str, Any] | None) -> dict[str, Any] | None:
        with _cache_lock:
            _cache[key] = (time.monotonic() + _CACHE_TTL, value)
        return value

    # Try static table first (fast path check)
    base = STATIC_CROP_PRICES.get(crop.lower())
    if not base:
        return _remember(None)

    # Attempt live fetch from eNAM (best-effort, short timeout)
    try:
        t0 = time.monotonic()
        resp = requests.get(
            "https://enam.gov.in/web/dashboard/modal-prices-api",
            params={"commodity": crop, "state": state or ""},
            timeout=5,
            headers={"Accept": "application/json"},
        )
        if resp.ok:
            data = resp.json()
            # eNAM returns a list of records; take most recent modal price
            records = data if isinstance(data, list) else data.get("data", [])
            if records:
                latest = records[0]
                modal_price = latest.get("Modal_Price") or latest.get("modal_price")
                if modal_price:
                    return _remember({
                        "price_inr_per_quintal": float(modal_price),
                        "avg_yield_q_per_ha": base["avg_yield_q_per_ha"],
                        "source": "enam_live",
                        "state": state,
                    })
        else:
            elapsed = time.monotonic() - t0
            log.warning("eNAM live fetch failed for crop=%s: status=%s elapsed=%.2fs", crop, resp.status_code, elapsed)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        log.warning("eNAM live fetch failed for crop=%s: error=%s elapsed=%.2fs", crop, type(exc).__name__, elapsed)

    return _remember({
        **base,
        "source": "static_apmc_2024",
    })


def compute_value_at_risk(
    crop: str,
    dependency: float,
    overall_stress: float,
    state: str | None = None,
) -> float | None:
    """
    Compute value at risk in INR per hectare:
      price_per_quintal × avg_yield_q_per_ha × dependency × overall_stress
    Returns None if price data is unavailable for the crop.
    """
    price_data = get_crop_price_inr(crop, state)
    if not price_data:
        return None
    price = price_data["price_inr_per_quintal"]
    yield_q = price_data["avg_yield_q_per_ha"]
    return round(price * yield_q * dependency * overall_stress, 0)
