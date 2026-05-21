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
# Factor 1 – Pesticide Exposure
# ──────────────────────────────────────────────────────────────────────────────

def score_pesticide_exposure(pesticide: dict[str, Any]) -> float:
    """
    Pesticide stress (0–1).
    ppm concentration uses a sigmoid centred at 10 ppm; frequency and recency
    are linear.  Pesticide data is OWID/FAO-derived and always present, so
    None fallbacks are defensive only.
    """
    ppm    = pesticide.get("usage_ppm") or 5.0
    freq   = pesticide.get("applications_per_month") or 2
    days   = pesticide.get("days_since_last_application") or 30
    t_mult = pesticide.get("toxicity_multiplier") or 1.0

    usage_stress   = _sigmoid_stress(float(ppm),  midpoint=10.0, steepness=0.22)
    freq_stress    = _linear_stress(float(freq),   0.0, 8.0)
    recency_stress = _clamp(1.0 - float(days) / 30.0)

    raw = (usage_stress * 0.45 + freq_stress * 0.30 + recency_stress * 0.25)
    return _clamp(raw * float(t_mult))


# ──────────────────────────────────────────────────────────────────────────────
# Factor 2 – Soil Fertility Rate
# ──────────────────────────────────────────────────────────────────────────────

# Neutral stress used when a sub-signal is genuinely unavailable (None).
# 0.5 means "unknown" — contributes neither good nor bad to the weighted score.
_NEUTRAL_STRESS = 0.5


def score_soil_fertility(
    soil: dict[str, Any],
    nasa: dict[str, Any],
) -> float:
    """
    Soil fertility stress (0–1).
    pH stress uses a two-sided sigmoid; other sub-signals are linear.
    When a value is None (source unavailable), that sub-signal contributes
    a neutral 0.5 stress so it does not fabricate a healthy or stressed signal.
    """
    ph         = soil.get("ph")
    soc        = soil.get("organic_carbon_g_per_kg")
    nitrogen   = soil.get("nitrogen_g_per_kg")
    compaction = soil.get("compaction_index")
    moisture   = nasa.get("root_zone_wetness")

    # pH — two-sided sigmoid around optimum 6.5
    if ph is None:
        ph_stress = _NEUTRAL_STRESS
    elif ph < 6.5:
        ph_stress = _clamp(_sigmoid_stress(6.5 - ph, midpoint=1.0, steepness=1.5))
    else:
        ph_stress = _clamp(_sigmoid_stress(ph - 6.5, midpoint=1.0, steepness=1.5))

    # Organic carbon — stress rises sharply below 1.5 g/kg
    if soc is None:
        carbon_stress = _NEUTRAL_STRESS
    else:
        carbon_stress = _clamp(_sigmoid_stress(1.5 - soc, midpoint=0.5, steepness=2.5))

    # Nitrogen
    if nitrogen is None:
        nitrogen_stress = _NEUTRAL_STRESS
    else:
        nitrogen_stress = _linear_stress(1.0 - nitrogen, 0.0, 1.0)

    # Soil moisture — bell curve around optimal 0.50
    if moisture is None:
        moisture_stress = _NEUTRAL_STRESS
    else:
        moisture_stress = _bell_curve_stress(float(moisture), optimum=0.50, tolerance=0.30)

    # Compaction
    if compaction is None:
        compaction_stress = _NEUTRAL_STRESS
    else:
        compaction_stress = _clamp(float(compaction))

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
    """
    Floral diversity stress (0–1).
    When NDVI or GBIF values are None (source unavailable), sub-signals
    contribute a neutral 0.5 rather than fabricating a healthy landscape.
    """
    ndvi_val      = ndvi.get("ndvi")
    flower_cov    = ndvi.get("flowering_coverage")
    patch_div     = ndvi.get("patch_diversity")
    species_count = gbif.get("species_count")  # 0 is valid real data

    ndvi_stress    = _linear_stress(0.35 - ndvi_val, 0.0, 0.35) if ndvi_val is not None else _NEUTRAL_STRESS
    flower_stress  = _linear_stress(0.25 - flower_cov, 0.0, 0.25) if flower_cov is not None else _NEUTRAL_STRESS
    patch_stress   = _linear_stress(0.5 - patch_div, 0.0, 0.5) if patch_div is not None else _NEUTRAL_STRESS
    species_stress = _clamp(1.0 - species_count / 12.0) if species_count is not None else _NEUTRAL_STRESS

    raw = (
        ndvi_stress    * 0.35 +
        flower_stress  * 0.25 +
        patch_stress   * 0.20 +
        species_stress * 0.20
    )
    return _clamp(raw)


def score_pollination_factor(visitation: dict[str, Any]) -> float:
    """
    Pollination factor stress (0–1).
    When visitation values are None (e.g. source is 'visitation_unavailable'),
    each sub-signal uses a neutral 0.5 so no fictional stress is added.
    """
    visit_ratio         = visitation.get("visitation_ratio")
    decline_rate        = visitation.get("decline_rate_12w")
    timing_disruption   = visitation.get("pollination_timing_disruption")
    flowering_success   = visitation.get("flowering_success_rate")
    recovery_volatility = visitation.get("recovery_volatility")

    visit_stress      = _linear_stress(0.75 - visit_ratio, 0.0, 0.75)    if visit_ratio is not None         else _NEUTRAL_STRESS
    decline_stress    = _clamp(decline_rate / 0.55)                        if decline_rate is not None        else _NEUTRAL_STRESS
    timing_stress     = _clamp(timing_disruption)                          if timing_disruption is not None   else _NEUTRAL_STRESS
    flowering_stress  = _linear_stress(0.65 - flowering_success, 0.0, 0.65) if flowering_success is not None else _NEUTRAL_STRESS
    volatility_stress = _clamp(recovery_volatility)                        if recovery_volatility is not None else _NEUTRAL_STRESS

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
    """
    Climate variability stress (0–1).
    When climate data is None (open_meteo_unavailable), sub-signals use
    a neutral 0.5 rather than fabricating a stress score.
    """
    temp_std     = climate.get("temp_std_c")
    total_precip = climate.get("total_precipitation_mm")
    precip_std   = climate.get("precip_std_mm")
    drought_idx  = climate.get("drought_index")

    if temp_std is None:
        temp_stress = _NEUTRAL_STRESS
    elif abs(lat) < 25.0:
        temp_stress = _linear_stress(float(temp_std), 8.0, 20.0)
    else:
        temp_stress = _linear_stress(float(temp_std), 4.0, 14.0)

    precip_stress     = _linear_stress(30.0 - float(total_precip), 0.0, 60.0) if total_precip is not None else _NEUTRAL_STRESS
    precip_var_stress = _linear_stress(float(precip_std), 2.0, 8.0)           if precip_std is not None    else _NEUTRAL_STRESS

    # Sigmoid drought stress — None means data unavailable, use neutral
    if drought_idx is None:
        drought_stress = _NEUTRAL_STRESS
    else:
        drought_stress = _clamp(_sigmoid_stress(float(drought_idx), midpoint=0.55, steepness=5.0))

    raw = (
        temp_stress       * 0.30 +
        precip_stress     * 0.30 +
        drought_stress    * 0.25 +
        precip_var_stress * 0.15
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 5 – Nesting Availability
# ──────────────────────────────────────────────────────────────────────────────

def score_nesting_availability(ndvi: dict[str, Any]) -> float:
    """
    Nesting availability stress (0–1).
    When NDVI values are None (source unavailable), sub-signals use
    a neutral 0.5 rather than fabricating a healthy nesting landscape.
    """
    bare_soil   = ndvi.get("bare_soil_fraction")
    hedgerow    = ndvi.get("hedgerow_density")
    dead_wood   = ndvi.get("dead_wood_index")
    disturbance = ndvi.get("disturbance_score")

    if bare_soil is None:
        bare_stress = _NEUTRAL_STRESS
    elif bare_soil > 0.30:
        bare_stress = _linear_stress(bare_soil - 0.30, 0.0, 0.45)
    else:
        bare_stress = _linear_stress(0.05 - bare_soil, 0.0, 0.05)

    hedge_stress = _linear_stress(0.30 - float(hedgerow), 0.0, 0.30) if hedgerow is not None else _NEUTRAL_STRESS
    dw_stress    = _linear_stress(0.20 - float(dead_wood), 0.0, 0.20) if dead_wood is not None else _NEUTRAL_STRESS
    dist_stress  = _clamp(float(disturbance)) if disturbance is not None else _NEUTRAL_STRESS

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

def compute_crop_risks(overall_stress: float, zone_id: str = "", geo_profile: dict = None) -> dict[str, str]:
    risks = {}
    for crop, dep in get_crop_dependency_for_zone(zone_id, geo_profile).items():
        impact = _clamp(dep * overall_stress)
        risks[crop] = _label_from_bands(impact, CROP_RISK_LABELS)
    return risks


def _anomaly_stress_floor(anomalies: list[dict[str, Any]]) -> float:
    critical_count = sum(1 for item in anomalies if item.get("severity") == "CRITICAL")
    warning_count = sum(1 for item in anomalies if item.get("severity") == "WARNING")
    critical_factors = {
        item.get("factor")
        for item in anomalies
        if item.get("severity") == "CRITICAL"
    }

    if critical_count >= 3 or len(critical_factors) >= 3:
        floor = 0.52
    elif critical_count == 2:
        floor = 0.45
    elif critical_count == 1:
        floor = 0.34
    else:
        floor = 0.0

    floor += min(0.10, warning_count * 0.02)
    return _clamp(floor)


def apply_anomaly_pressure(
    scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
    zone_id: str = "",
    geo_profile: dict | None = None,
) -> dict[str, Any]:
    """
    Guardrail the composite score so multiple CRITICAL findings cannot be
    hidden by a low weighted average. Factor scores remain unchanged; only the
    displayed overall stress, activity label, stress label, and crop risks are
    adjusted when anomaly severity warrants it.
    """
    floor = _anomaly_stress_floor(anomalies)
    current_stress = float(scores.get("overall_stress", 0.0) or 0.0)
    adjusted_stress = _clamp(max(current_stress, floor))
    if adjusted_stress == current_stress:
        scores["anomaly_pressure_adjustment"] = {
            "applied": False,
            "stress_floor": _r2(floor),
            "original_overall_stress": _r2(current_stress),
        }
        return scores

    scores = dict(scores)
    scores["overall_stress"] = _r2(adjusted_stress)
    scores["activity_score"] = _r2((1.0 - adjusted_stress) * 100)
    scores["activity_label"] = _label_from_bands(scores["activity_score"], ACTIVITY_SCORE_LABELS)
    scores["pollination_stress_index"] = _label_from_bands(adjusted_stress, STRESS_INDEX_THRESHOLDS)
    scores["crop_risk"] = compute_crop_risks(adjusted_stress, zone_id=zone_id, geo_profile=geo_profile)
    scores["anomaly_pressure_adjustment"] = {
        "applied": True,
        "stress_floor": _r2(floor),
        "original_overall_stress": _r2(current_stress),
        "adjusted_overall_stress": _r2(adjusted_stress),
        "critical_count": sum(1 for item in anomalies if item.get("severity") == "CRITICAL"),
        "warning_count": sum(1 for item in anomalies if item.get("severity") == "WARNING"),
    }
    return scores


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
    geo_profile = raw.get("_meta", {}).get("geo_profile", None)

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
    effective_weights = get_factor_weights_for_zone(zone_id, geo_profile)

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
        for crop, dep in get_crop_dependency_for_zone(zone_id, geo_profile).items()
    }
    crop_risk = compute_crop_risks(overall_stress, zone_id=zone_id, geo_profile=geo_profile)

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
