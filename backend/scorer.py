"""
scorer.py
=========
Normalises raw environmental data and computes the five factor scores plus
the overall Pollinator Activity Score.

Factor stress scores are in [0, 1] where 1 = maximum stress.
The activity score is (1 - weighted_stress_sum) * 100 where 100 = fully healthy.
"""

import math
from typing import Any

from config import (
    CROP_POLLINATION_DEPENDENCY,
    CROP_RISK_LABELS,
    FACTOR_WEIGHTS,
    HABITAT_WEIGHTS,
    ACTIVITY_SCORE_LABELS,
    STRESS_INDEX_THRESHOLDS,
)


# ──────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _linear_stress(value: float, lo_ok: float, hi_stress: float) -> float:
    """
    Maps a value to [0, 1] stress where:
        value ≤ lo_ok    → 0.0  (no stress)
        value ≥ hi_stress → 1.0  (full stress)
    """
    if value <= lo_ok:
        return 0.0
    if value >= hi_stress:
        return 1.0
    return (value - lo_ok) / (hi_stress - lo_ok)


def _bell_curve_stress(value: float, optimum: float, tolerance: float) -> float:
    """
    Gaussian-shaped stress score: 0 at optimum, rising to 1 as
    |value - optimum| grows beyond tolerance.
    """
    deviation = abs(value - optimum) / tolerance
    stress = 1.0 - math.exp(-0.5 * deviation ** 2)
    return _clamp(stress)


def _label_from_bands(value: float, bands: list) -> str:
    """Return the label for a numeric value given ordered (lo, hi, label) bands."""
    for lo, hi, label in bands:
        if lo <= value <= hi:
            return label
    # Edge: clamp to nearest band
    return bands[-1][2] if value > bands[-1][1] else bands[0][2]


def _r2(value: float) -> float:
    """Round to 2 decimal places."""
    return round(value, 2)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 1 – Pesticide Exposure  (weight 0.35)
# ──────────────────────────────────────────────────────────────────────────────

def score_pesticide_exposure(pesticide: dict[str, Any]) -> float:
    """
    Compute pesticide stress score [0, 1].

    Sub-components:
        usage_stress    – ppm concentration (above 5 ppm starts to matter)
        freq_stress     – application frequency per month
        recency_stress  – how recently applied (recent = high stress)
        toxicity_mult   – pesticide-type multiplier
    """
    ppm    = pesticide.get("usage_ppm", 5.0)
    freq   = pesticide.get("applications_per_month", 2)
    days   = pesticide.get("days_since_last_application", 30)
    t_mult = pesticide.get("toxicity_multiplier", 1.0)

    # ppm stress: 0 at 0 ppm, 1.0 at 20+ ppm
    usage_stress = _linear_stress(ppm, 0.0, 20.0)

    # Frequency stress: 0 at 0/month, 1.0 at 8+/month
    freq_stress = _linear_stress(float(freq), 0.0, 8.0)

    # Recency stress: 1.0 if applied today, 0.0 after 30 days
    recency_stress = _clamp(1.0 - days / 30.0)

    # Weighted combination
    raw = (usage_stress * 0.45 + freq_stress * 0.30 + recency_stress * 0.25)

    # Apply toxicity multiplier (capped at 1.0)
    return _clamp(raw * t_mult)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 2 – Soil Fertility Rate  (weight 0.25)
# ──────────────────────────────────────────────────────────────────────────────

def score_soil_fertility(
    soil: dict[str, Any],
    nasa: dict[str, Any],
) -> float:
    """
    Compute soil fertility stress score [0, 1].

    Sub-components:
        ph_stress        – bell curve at optimum pH 6.5
        carbon_stress    – below 1.5 g/kg is concerning
        nitrogen_stress  – below 1.0 g/kg is concerning
        moisture_stress  – from NASA POWER root-zone wetness
        compaction_stress
    """
    ph         = soil.get("ph", 6.5)
    soc        = soil.get("organic_carbon_g_per_kg", 1.8)
    nitrogen   = soil.get("nitrogen_g_per_kg", 1.2)
    compaction = soil.get("compaction_index", 0.3)
    moisture   = nasa.get("root_zone_wetness", 0.45)  # 0–1

    # pH: optimum 6.5, tolerance 1.0
    ph_stress = _bell_curve_stress(ph, 6.5, 1.0)

    # Organic carbon: below 1.5 increases stress
    carbon_stress = _linear_stress(1.5 - soc, 0.0, 1.5)  # inverted

    # Nitrogen: below 1.0 increases stress
    nitrogen_stress = _linear_stress(1.0 - nitrogen, 0.0, 1.0)

    # Moisture: stress at extremes (< 0.2 dry stress, > 0.85 waterlog)
    if moisture < 0.5:
        moisture_stress = _linear_stress(0.2 - moisture, 0.0, 0.2)
    else:
        moisture_stress = _linear_stress(moisture - 0.85, 0.0, 0.15)

    # Compaction
    compaction_stress = _clamp(compaction)

    raw = (
        ph_stress        * 0.25 +
        carbon_stress    * 0.25 +
        nitrogen_stress  * 0.20 +
        moisture_stress  * 0.15 +
        compaction_stress * 0.15
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 3 – Floral Diversity  (weight 0.20)
# ──────────────────────────────────────────────────────────────────────────────

def score_floral_diversity(
    ndvi: dict[str, Any],
    gbif: dict[str, Any],
) -> float:
    """
    Compute floral diversity stress score [0, 1].

    Low NDVI, few species, and low flowering coverage → high stress.
    """
    ndvi_val      = ndvi.get("ndvi", 0.50)
    flower_cov    = ndvi.get("flowering_coverage", 0.35)
    patch_div     = ndvi.get("patch_diversity", 0.45)
    species_count = gbif.get("species_count", 5)

    # NDVI stress: below 0.35 is sparse vegetation
    ndvi_stress = _linear_stress(0.35 - ndvi_val, 0.0, 0.35)

    # Flowering coverage stress: below 0.25 is low
    flower_stress = _linear_stress(0.25 - flower_cov, 0.0, 0.25)

    # Patch diversity stress: low = uniform monoculture
    patch_stress = _linear_stress(0.5 - patch_div, 0.0, 0.5)

    # Species richness stress: < 10 is limited; < 2 is critical
    species_stress = _clamp(1.0 - species_count / 12.0)

    raw = (
        ndvi_stress    * 0.35 +
        flower_stress  * 0.25 +
        patch_stress   * 0.20 +
        species_stress * 0.20
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 4 – Climate Variability  (weight 0.12)
# ──────────────────────────────────────────────────────────────────────────────

def score_climate_variability(climate: dict[str, Any]) -> float:
    """
    Compute climate variability stress score [0, 1].

    High temperature standard deviation, low rainfall, and high drought
    index contribute to stress.
    """
    temp_std      = climate.get("temp_std_c", 4.0)
    total_precip  = climate.get("total_precipitation_mm", 48.0)
    precip_std    = climate.get("precip_std_mm", 3.0)
    drought_idx   = climate.get("drought_index", 0.35)

    # Temperature variance stress: SD > 8°C is stressful
    temp_stress = _linear_stress(temp_std, 4.0, 14.0)

    # Precipitation deficit stress: below 30 mm/30 days
    precip_stress = _linear_stress(30.0 - total_precip, 0.0, 60.0)

    # Precipitation irregularity
    precip_var_stress = _linear_stress(precip_std, 2.0, 8.0)

    # Drought index
    drought_stress = _clamp(drought_idx)

    raw = (
        temp_stress       * 0.30 +
        precip_stress     * 0.30 +
        precip_var_stress * 0.20 +
        drought_stress    * 0.20
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 5 – Nesting Availability  (weight 0.08)
# ──────────────────────────────────────────────────────────────────────────────

def score_nesting_availability(ndvi: dict[str, Any]) -> float:
    """
    Compute nesting availability stress score [0, 1].

    Considers bare soil fraction, hedgerow density (inverted),
    dead wood index (inverted), and general disturbance.
    """
    bare_soil    = ndvi.get("bare_soil_fraction", 0.25)   # too much = bad
    hedgerow     = ndvi.get("hedgerow_density", 0.30)      # more = good
    dead_wood    = ndvi.get("dead_wood_index", 0.20)       # more = good
    disturbance  = ndvi.get("disturbance_score", 0.35)

    # Bare soil: >0.30 excessive, monoculture; <0.05 no ground-nesting sites
    if bare_soil > 0.30:
        bare_stress = _linear_stress(bare_soil - 0.30, 0.0, 0.45)
    else:
        bare_stress = _linear_stress(0.05 - bare_soil, 0.0, 0.05)

    # Hedgerow: lower → more stress
    hedge_stress = _linear_stress(0.30 - hedgerow, 0.0, 0.30)

    # Dead wood: lower → more stress
    dw_stress = _linear_stress(0.20 - dead_wood, 0.0, 0.20)

    # Disturbance: direct stress
    dist_stress = _clamp(disturbance)

    raw = (
        bare_stress  * 0.30 +
        hedge_stress * 0.25 +
        dw_stress    * 0.20 +
        dist_stress  * 0.25
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Habitat suitability score (0–100, higher = more suitable)
# ──────────────────────────────────────────────────────────────────────────────

def compute_habitat_suitability(
    floral_stress: float,
    nesting_stress: float,
    soil_stress: float,
) -> float:
    weighted = (
        floral_stress  * HABITAT_WEIGHTS["floral_diversity"] +
        nesting_stress * HABITAT_WEIGHTS["nesting_availability"] +
        soil_stress    * HABITAT_WEIGHTS["soil_fertility"]
    )
    return _r2((1.0 - weighted) * 100)


# ──────────────────────────────────────────────────────────────────────────────
# Crop risk
# ──────────────────────────────────────────────────────────────────────────────

def compute_crop_risks(overall_stress: float) -> dict[str, str]:
    """
    For each crop, compute risk as: dependency × overall_stress → label.
    """
    risks = {}
    for crop, dep in CROP_POLLINATION_DEPENDENCY.items():
        impact = _clamp(dep * overall_stress)
        risks[crop] = _label_from_bands(impact, CROP_RISK_LABELS)
    return risks


# ──────────────────────────────────────────────────────────────────────────────
# Top-level scorer
# ──────────────────────────────────────────────────────────────────────────────

def compute_all_scores(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Accept the raw data bundle from data_fetcher.fetch_all() and return
    a fully scored dict suitable for downstream use by anomaly_detector and main.

    Returns
    -------
    {
        "factor_scores": {
            "pesticide_exposure":  float,   # 0–1 stress
            "soil_fertility":      float,
            "floral_diversity":    float,
            "climate_variability": float,
            "nesting_availability": float,
        },
        "overall_stress":           float,   # 0–1 weighted sum
        "activity_score":           float,   # 0–100
        "activity_label":           str,
        "habitat_suitability_score": float,  # 0–100
        "pollination_stress_index": str,
        "crop_risk":                dict[str, str],
        "contribution_scores":      dict[str, float],  # weighted contribution
    }
    """
    climate   = raw["climate"]
    nasa      = raw["nasa"]
    soil      = raw["soil"]
    ndvi      = raw["ndvi"]
    gbif      = raw["gbif"]
    pesticide = raw["pesticide"]

    # ── Compute raw factor stress scores ────────────────────────────────────
    f_pest    = score_pesticide_exposure(pesticide)
    f_soil    = score_soil_fertility(soil, nasa)
    f_floral  = score_floral_diversity(ndvi, gbif)
    f_climate = score_climate_variability(climate)
    f_nesting = score_nesting_availability(ndvi)

    factor_scores = {
        "pesticide_exposure":   _r2(f_pest),
        "soil_fertility":       _r2(f_soil),
        "floral_diversity":     _r2(f_floral),
        "climate_variability":  _r2(f_climate),
        "nesting_availability": _r2(f_nesting),
    }

    # ── Weighted stress sum ──────────────────────────────────────────────────
    overall_stress = sum(
        factor_scores[k] * FACTOR_WEIGHTS[k]
        for k in FACTOR_WEIGHTS
    )
    overall_stress = _clamp(round(overall_stress, 4))

    # ── Activity score ───────────────────────────────────────────────────────
    activity_score = _r2((1.0 - overall_stress) * 100)
    activity_label = _label_from_bands(activity_score, ACTIVITY_SCORE_LABELS)

    # ── Contribution scores (how much each factor drives down the score) ─────
    contribution_scores = {
        k: _r2(factor_scores[k] * FACTOR_WEIGHTS[k] * 100)
        for k in factor_scores
    }

    # ── Habitat suitability ──────────────────────────────────────────────────
    habitat_score = compute_habitat_suitability(f_floral, f_nesting, f_soil)

    # ── Stress index label ───────────────────────────────────────────────────
    stress_label = _label_from_bands(overall_stress, STRESS_INDEX_THRESHOLDS)

    # ── Crop risk ────────────────────────────────────────────────────────────
    crop_risk = compute_crop_risks(overall_stress)

    return {
        "factor_scores":            factor_scores,
        "overall_stress":           _r2(overall_stress),
        "activity_score":           activity_score,
        "activity_label":           activity_label,
        "habitat_suitability_score": habitat_score,
        "pollination_stress_index": stress_label,
        "crop_risk":                crop_risk,
        "contribution_scores":      contribution_scores,
    }
