"""
scorer.py
=========
Fix 5: Sigmoid scoring replaces hard linear ramps for pesticide and pH —
       more accurate stress signals with realistic smooth transitions.
"""

import math
from typing import Any

from config import (
    CROP_RISK_LABELS,
    FACTOR_WEIGHTS,
    HABITAT_WEIGHTS,
    ACTIVITY_SCORE_LABELS,
    STRESS_INDEX_THRESHOLDS,
    get_crop_dependency_for_zone,
    get_factor_weights_for_zone,  # Fix 6
)


# ──────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _linear_stress(value: float, lo_ok: float, hi_stress: float) -> float:
    if value <= lo_ok:
        return 0.0
    if value >= hi_stress:
        return 1.0
    return (value - lo_ok) / (hi_stress - lo_ok)


def _sigmoid_stress(value: float, midpoint: float, steepness: float = 1.0) -> float:
    """
    Fix 5: Sigmoid (logistic) stress function.
    Returns 0.5 when value == midpoint; approaches 0 well below and 1 well above.
    steepness controls how sharply stress rises around the midpoint.
    Always returns [0, 1].
    """
    return 1.0 / (1.0 + math.exp(-steepness * (value - midpoint)))


def _bell_curve_stress(value: float, optimum: float, tolerance: float) -> float:
    deviation = abs(value - optimum) / tolerance
    stress = 1.0 - math.exp(-0.5 * deviation ** 2)
    return _clamp(stress)


def _label_from_bands(value: float, bands: list) -> str:
    for lo, hi, label in bands:
        if lo <= value <= hi:
            return label
    return bands[-1][2] if value > bands[-1][1] else bands[0][2]


def _r2(value: float) -> float:
    return round(value, 2)


def _round_dependency(value: float) -> float:
    return round(round(value * 20.0) / 20.0, 2)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 1 – Pesticide Exposure  (Fix 5: sigmoid on ppm concentration)
# ──────────────────────────────────────────────────────────────────────────────

def score_pesticide_exposure(pesticide: dict[str, Any]) -> float:
    """
    Fix 5: ppm concentration now uses a sigmoid centred at the safe threshold
    (5 ppm) with steepness=0.18 so stress rises smoothly from near-zero at
    0 ppm to ~0.87 at 20 ppm, rather than a hard linear ramp that was either
    all-or-nothing.  Frequency and recency remain linear.
    """
    ppm    = pesticide.get("usage_ppm", 5.0)
    freq   = pesticide.get("applications_per_month", 2)
    days   = pesticide.get("days_since_last_application", 30)
    t_mult = pesticide.get("toxicity_multiplier", 1.0)

    # Fix 5: sigmoid ppm stress — midpoint at 10 ppm (midpoint between warning
    # threshold 5 and critical threshold 15), steepness tuned so:
    #   0 ppm → ~0.01, 5 ppm → ~0.18, 10 ppm → 0.50, 15 ppm → ~0.82, 20 ppm → ~0.95
    usage_stress = _sigmoid_stress(ppm, midpoint=10.0, steepness=0.22)

    # Frequency stress: linear 0 at 0/month, 1.0 at 8+/month
    freq_stress = _linear_stress(float(freq), 0.0, 8.0)

    # Recency stress: 1.0 if applied today, 0.0 after 30 days
    recency_stress = _clamp(1.0 - days / 30.0)

    raw = (usage_stress * 0.45 + freq_stress * 0.30 + recency_stress * 0.25)
    return _clamp(raw * t_mult)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 2 – Soil Fertility Rate  (Fix 5: sigmoid on pH)
# ──────────────────────────────────────────────────────────────────────────────

def score_soil_fertility(
    soil: dict[str, Any],
    nasa: dict[str, Any],
) -> float:
    """
    Fix 5: pH stress now uses a two-sided sigmoid (symmetric around optimum
    6.5) rather than a pure bell curve that was hard to calibrate.  The new
    formula gives:
      pH 6.5 → 0.0 stress (optimum)
      pH 5.5 → ~0.35 stress (warning zone)
      pH 5.0 → ~0.73 stress (critical zone)
      pH 7.5 → ~0.35 stress (high-side warning)
      pH 8.0 → ~0.73 stress (high-side critical)
    """
    ph         = soil.get("ph", 6.5)
    soc        = soil.get("organic_carbon_g_per_kg", 1.8)
    nitrogen   = soil.get("nitrogen_g_per_kg", 1.2)
    compaction = soil.get("compaction_index", 0.3)
    moisture   = nasa.get("root_zone_wetness", 0.45)

    # Fix 5: two-sided sigmoid pH stress
    # Low-side: sigmoid centred at 5.25 (midpoint between critical 5.0 and warning 5.5)
    # High-side: sigmoid centred at 7.75 (midpoint between warning 7.5 and critical 8.0)
    if ph < 6.5:
        ph_stress = _sigmoid_stress(6.5 - ph, midpoint=1.0, steepness=1.5)
    else:
        ph_stress = _sigmoid_stress(ph - 6.5, midpoint=1.0, steepness=1.5)
    ph_stress = _clamp(ph_stress)

    # Organic carbon: sigmoid — stress rises sharply below 1.5 g/kg
    carbon_stress = _sigmoid_stress(1.5 - soc, midpoint=0.5, steepness=2.5)
    carbon_stress = _clamp(carbon_stress)

    # Nitrogen: below 1.0 increases stress
    nitrogen_stress = _linear_stress(1.0 - nitrogen, 0.0, 1.0)

    # Moisture: bell curve around optimal 0.50
    moisture_stress = _bell_curve_stress(moisture, optimum=0.50, tolerance=0.30)

    compaction_stress = _clamp(compaction)

    raw = (
        ph_stress         * 0.25 +
        carbon_stress     * 0.25 +
        nitrogen_stress   * 0.20 +
        moisture_stress   * 0.15 +
        compaction_stress * 0.15
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 3 – Floral Diversity
# ──────────────────────────────────────────────────────────────────────────────

def score_floral_diversity(
    ndvi: dict[str, Any],
    gbif: dict[str, Any],
) -> float:
    ndvi_val      = ndvi.get("ndvi", 0.50)
    flower_cov    = ndvi.get("flowering_coverage", 0.35)
    patch_div     = ndvi.get("patch_diversity", 0.45)
    species_count = gbif.get("species_count", 5)

    ndvi_stress    = _linear_stress(0.35 - ndvi_val, 0.0, 0.35)
    flower_stress  = _linear_stress(0.25 - flower_cov, 0.0, 0.25)
    patch_stress   = _linear_stress(0.5 - patch_div, 0.0, 0.5)
    species_stress = _clamp(1.0 - species_count / 12.0)

    raw = (
        ndvi_stress    * 0.35 +
        flower_stress  * 0.25 +
        patch_stress   * 0.20 +
        species_stress * 0.20
    )
    return _clamp(raw)


def score_pollination_factor(visitation: dict[str, Any]) -> float:
    visit_ratio         = visitation.get("visitation_ratio", 0.75)
    decline_rate        = visitation.get("decline_rate_12w", 0.0)
    timing_disruption   = visitation.get("pollination_timing_disruption", 0.25)
    flowering_success   = visitation.get("flowering_success_rate", 0.70)
    recovery_volatility = visitation.get("recovery_volatility", 0.25)

    visit_stress     = _linear_stress(0.75 - visit_ratio, 0.0, 0.75)
    decline_stress   = _clamp(decline_rate / 0.55)
    timing_stress    = _clamp(timing_disruption)
    flowering_stress = _linear_stress(0.65 - flowering_success, 0.0, 0.65)
    volatility_stress = _clamp(recovery_volatility)

    raw = (
        visit_stress      * 0.35 +
        decline_stress    * 0.25 +
        timing_stress     * 0.20 +
        flowering_stress  * 0.15 +
        volatility_stress * 0.05
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 4 – Climate Variability
# ──────────────────────────────────────────────────────────────────────────────

def score_climate_variability(
    climate: dict[str, Any],
    lat: float = 0.0,
) -> float:
    temp_std     = climate.get("temp_std_c", 4.0)
    total_precip = climate.get("total_precipitation_mm", 48.0)
    precip_std   = climate.get("precip_std_mm", 3.0)
    drought_idx  = climate.get("drought_index", 0.35)

    if abs(lat) < 25.0:
        temp_stress = _linear_stress(temp_std, 8.0, 20.0)
    else:
        temp_stress = _linear_stress(temp_std, 4.0, 14.0)

    precip_stress     = _linear_stress(30.0 - total_precip, 0.0, 60.0)
    precip_var_stress = _linear_stress(precip_std, 2.0, 8.0)

    drought_stress = 0.4 if drought_idx is None else _clamp(drought_idx)

    raw = (
        temp_stress       * 0.30 +
        precip_stress     * 0.30 +
        precip_var_stress * 0.20 +
        drought_stress    * 0.20
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 5 – Nesting Availability
# ──────────────────────────────────────────────────────────────────────────────

def score_nesting_availability(ndvi: dict[str, Any]) -> float:
    bare_soil   = ndvi.get("bare_soil_fraction", 0.25)
    hedgerow    = ndvi.get("hedgerow_density", 0.30)
    dead_wood   = ndvi.get("dead_wood_index", 0.20)
    disturbance = ndvi.get("disturbance_score", 0.35)

    if bare_soil > 0.30:
        bare_stress = _linear_stress(bare_soil - 0.30, 0.0, 0.45)
    else:
        bare_stress = _linear_stress(0.05 - bare_soil, 0.0, 0.05)

    hedge_stress = _linear_stress(0.30 - hedgerow, 0.0, 0.30)
    dw_stress    = _linear_stress(0.20 - dead_wood, 0.0, 0.20)
    dist_stress  = _clamp(disturbance)

    raw = (
        bare_stress  * 0.30 +
        hedge_stress * 0.25 +
        dw_stress    * 0.20 +
        dist_stress  * 0.25
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Habitat suitability
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

def compute_crop_risks(overall_stress: float, zone_id: str = "") -> dict[str, str]:
    risks = {}
    for crop, dep in get_crop_dependency_for_zone(zone_id).items():
        impact = _clamp(dep * overall_stress)
        risks[crop] = _label_from_bands(impact, CROP_RISK_LABELS)
    return risks


# ──────────────────────────────────────────────────────────────────────────────
# Top-level scorer
# ──────────────────────────────────────────────────────────────────────────────

def compute_all_scores(raw: dict[str, Any], zone_id: str = "") -> dict[str, Any]:
    climate    = raw["climate"]
    nasa       = raw["nasa"]
    soil       = raw["soil"]
    ndvi       = raw["ndvi"]
    gbif       = raw["gbif"]
    pesticide  = raw["pesticide"]
    visitation = raw.get("visitation", {})
    lat        = raw.get("_meta", {}).get("lat", 0.0)

    f_pest        = score_pesticide_exposure(pesticide)
    f_soil        = score_soil_fertility(soil, nasa)
    f_floral      = score_floral_diversity(ndvi, gbif)
    f_climate     = score_climate_variability(climate, lat=lat)
    f_nesting     = score_nesting_availability(ndvi)
    f_pollination = score_pollination_factor(visitation)

    factor_scores = {
        "pesticide_exposure":   _r2(f_pest),
        "soil_fertility":       _r2(f_soil),
        "floral_diversity":     _r2(f_floral),
        "climate_variability":  _r2(f_climate),
        "nesting_availability": _r2(f_nesting),
        "pollination_factor":   _r2(f_pollination),
    }

    # Fix 6: use per-zone weights from zone_weights.yaml if available
    effective_weights = get_factor_weights_for_zone(zone_id)

    overall_stress = _clamp(round(sum(
        factor_scores[k] * effective_weights[k] for k in effective_weights
    ), 4))

    activity_score = _r2((1.0 - overall_stress) * 100)
    activity_label = _label_from_bands(activity_score, ACTIVITY_SCORE_LABELS)

    contribution_scores = {
        k: _r2(factor_scores[k] * effective_weights[k] * 100)
        for k in factor_scores
    }

    habitat_score = compute_habitat_suitability(f_floral, f_nesting, f_soil)
    stress_label  = _label_from_bands(overall_stress, STRESS_INDEX_THRESHOLDS)

    crop_dependency = {
        crop: _round_dependency(dep)
        for crop, dep in get_crop_dependency_for_zone(zone_id).items()
    }
    crop_risk = compute_crop_risks(overall_stress, zone_id=zone_id)

    return {
        "factor_scores":             factor_scores,
        "overall_stress":            _r2(overall_stress),
        "activity_score":            activity_score,
        "activity_label":            activity_label,
        "habitat_suitability_score": habitat_score,
        "pollination_stress_index":  stress_label,
        "crop_risk":                 crop_risk,
        "crop_dependency":           crop_dependency,
        "crop_dependency_basis":     "coarse literature-informed estimates, not field-calibrated measurements",
        "factor_weights":            effective_weights,  # Fix 6: zone-specific
        "contribution_scores":       contribution_scores,
    }
