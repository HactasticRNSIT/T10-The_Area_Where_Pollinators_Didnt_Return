"""
scorer.py
=========
Fix 5: Sigmoid scoring replaces hard linear ramps for pesticide and pH —
       more accurate stress signals with realistic smooth transitions.
"""

import math
from typing import Any

__all__ = [
    "compute_all_scores",
    "score_pesticide_exposure",
    "score_soil_fertility",
]

from config import (
    CROP_RISK_LABELS,
    FACTOR_WEIGHTS,
    HABITAT_WEIGHTS,
    STRESS_INDEX_THRESHOLDS,
    ACTIVITY_SCORE_LABELS,
    ANOMALY_THRESHOLDS as _GLOBAL_T,
    INTERACTION_PENALTIES,
    INTERACTION_STRESS_THRESHOLD,
    get_anomaly_thresholds_for_zone,
    get_crop_dependency_for_zone,
    get_factor_weights_for_zone,
    get_species_norm_for_zone,
    CROP_FACTOR_AFFINITY,
    SCORING_CONSTANTS as _SC,
)  # Fix 6 + Round-3


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
    """
    Gaussian bell-curve stress.

    Returns 0.0 when value == optimum (no stress at the ideal point) and
    approaches 1.0 as deviation grows.

    Parameters
    ----------
    value     : float  Observed value.
    optimum   : float  Ideal value (zero-stress point).
    tolerance : float  Scale parameter.  At |value - optimum| == tolerance the
                       stress reaches 1 - exp(-0.5) ≈ 0.393 (half-Gaussian).

    Calibration
    -----------
    Used for soil moisture with optimum=0.50, tolerance=0.30 (NASA POWER
    GWETROOT scale).  At root_zone_wetness=0.20 (field stress threshold) the
    stress is ≈ 0.61; at 0.80 (waterlogging) it is also ≈ 0.61, which is
    consistent with the symmetric crop-water stress response curves in FAO
    Irrigation and Drainage Paper 56.
    """
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


# ──────────────────────────────────────────────────────────────────────────────
# Factor 1 – Pesticide Exposure
# ──────────────────────────────────────────────────────────────────────────────

def score_pesticide_exposure(pesticide: dict[str, Any]) -> float:
    """
    Pesticide stress (0–1).

    Sub-signals
    -----------
    usage_stress   (40% weight): sigmoid centred at 10 ppm (EFSA 2023 bee-health
        midpoint).  0 ppm → ~0.31 stress (background toxin pressure is always
        present in modern agriculture); 20 ppm → ~0.81 stress.
        _NEUTRAL_STRESS (0.5) here means concentration data is missing — we
        cannot distinguish a pesticide-free field from an unmonitored one.
    freq_stress    (35% weight): linear, saturates at 8 applications/month
        (ICAR intensive-use ceiling).  0 applications → 0.0 stress.
        Zero is a legitimate value (organic farms).
    recency_stress (25% weight): linear decay; stress = 0 when last application
        is 30+ days ago; stress = 1 at day 0.

    Inputs expected
    ---------------
    usage_ppm                : float | None   Pesticide concentration in field runoff.
    applications_per_month   : float | None   Spray events in the past 30 days.
    days_since_last_application : float | None  Days since the most recent spray.
    toxicity_multiplier      : float | None   Crop-type multiplier (1.0 = pyrethroid baseline).

    Calibration sources
    -------------------
    - EFSA 2023 Bee Health Report (usage sigmoid midpoint 10 ppm)
    - ICAR Crop Protection Norms for India (frequency ceiling 8/month)
    """
    ppm = pesticide.get("usage_ppm")
    if ppm is None:
        ppm = 5.0
    else:
        ppm = float(ppm)

    freq = pesticide.get("applications_per_month")
    if freq is None:
        freq = 2.0
    else:
        freq = float(freq)

    days = pesticide.get("days_since_last_application")
    if days is None:
        days = 30.0
    else:
        days = float(days)

    t_mult = pesticide.get("toxicity_multiplier")
    if t_mult is None:
        t_mult = 1.0
    else:
        t_mult = float(t_mult)

    usage_stress   = _sigmoid_stress(ppm,  midpoint=_SC["pesticide_ppm_midpoint"],
                                     steepness=_SC["pesticide_ppm_steepness"])
    freq_stress    = _linear_stress(freq, 0.0, _SC["pesticide_freq_max"])
    recency_stress = _clamp(1.0 - days / _SC["pesticide_recency_days"])

    raw = (
        usage_stress * 0.40 +
        freq_stress * 0.35 +
        recency_stress * 0.25
    )
    return _clamp(raw * t_mult)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 2 – Soil Fertility Rate
# ──────────────────────────────────────────────────────────────────────────────

# Neutral stress used when a sub-signal is genuinely unavailable (None).
# 0.5 means "unknown" — contributes neither good nor bad to the weighted score.
_NEUTRAL_STRESS = 0.5


def score_soil_fertility(
    soil: dict[str, Any],
    nasa: dict[str, Any],
    climate: dict[str, Any] | None = None,
) -> float:
    """
    Soil fertility stress (0–1).

    Sub-signals
    -----------
    ph_stress         (25% weight): two-sided sigmoid around optimum 6.5
        (FAO global consensus; Fageria & Baligar 2008).  Half-max stress
        at ±1 pH unit deviation.  _NEUTRAL_STRESS (0.5) when pH missing.
    carbon_stress     (25% weight): sigmoid stress below 1.5 g/kg SOC threshold
        (matches ANOMALY_THRESHOLDS organic_carbon_low_warning).
    nitrogen_stress   (20% weight): linear; 0 stress at ≥1.0 g/kg, full stress
        at 0 g/kg (ICAR minimum adequate nitrogen for cropland).
    moisture_stress   (15% weight): bell-curve around 0.50 (NASA POWER GWETROOT
        optimal; FAO Irrigation Paper 56 field-capacity proxy).
    compaction_stress (15% weight): raw SoilGrids bulk-density derived index.

    _NEUTRAL_STRESS (0.5) on any sub-signal means the source was unavailable —
    it does NOT mean the soil is average; it means we genuinely cannot assess it.

    Inputs expected
    ---------------
    soil.ph                        : float | None  pH (dimensionless, 0–14).
    soil.organic_carbon_g_per_kg   : float | None  SOC in g/kg.
    soil.nitrogen_g_per_kg         : float | None  Total N in g/kg.
    soil.compaction_index          : float | None  Derived compaction (0–1).
    nasa.root_zone_wetness         : float | None  NASA POWER GWETROOT (0–1).

    Calibration sources
    -------------------
    - FAO Soils Portal (pH optimum)
    - ISRIC SoilGrids SOC dataset documentation
    - FAO Irrigation and Drainage Paper 56 (soil moisture optimum)
    """
    ph         = soil.get("ph")
    soc        = soil.get("organic_carbon_g_per_kg")
    nitrogen   = soil.get("nitrogen_g_per_kg")
    compaction = soil.get("compaction_index")
    moisture   = nasa.get("root_zone_wetness")

    # pH — two-sided sigmoid around optimum 6.5
    if ph is None:
        ph_stress = _NEUTRAL_STRESS
    elif float(ph) < _SC["soil_ph_optimum"]:
        ph_stress = _clamp(_sigmoid_stress(
            _SC["soil_ph_optimum"] - float(ph),
            midpoint=_SC["soil_ph_midpoint_deviation"],
            steepness=_SC["soil_ph_tolerance_steepness"],
        ))
    else:
        ph_stress = _clamp(_sigmoid_stress(
            float(ph) - _SC["soil_ph_optimum"],
            midpoint=_SC["soil_ph_midpoint_deviation"],
            steepness=_SC["soil_ph_tolerance_steepness"],
        ))

    # Organic carbon — stress rises sharply below 1.5 g/kg
    if soc is None:
        carbon_stress = _NEUTRAL_STRESS
    else:
        carbon_stress = _clamp(_sigmoid_stress(
            _SC["soil_soc_stress_threshold"] - float(soc),
            midpoint=_SC["soil_soc_sigmoid_midpoint"],
            steepness=_SC["soil_soc_sigmoid_steepness"],
        ))

    # Nitrogen
    if nitrogen is None:
        nitrogen_stress = _NEUTRAL_STRESS
    else:
        nitrogen_stress = _linear_stress(1.0 - float(nitrogen), 0.0, 1.0)

    # Soil moisture — bell curve around optimal 0.50
    if moisture is None:
        moisture_stress = _NEUTRAL_STRESS
    else:
        moisture_stress = _bell_curve_stress(
            float(moisture),
            optimum=_SC["soil_moisture_optimum"],
            tolerance=_SC["soil_moisture_tolerance"],
        )

    # Compaction
    if compaction is None:
        compaction_stress = _NEUTRAL_STRESS
    else:
        compaction_stress = _clamp(float(compaction))

    # 6.1 Microbial proxy
    temp_c = climate.get("temp_mean_c") if climate else None
    
    if soc is None:
        soc_favour = 0.5
    else:
        soc_favour = _clamp(float(soc) / 3.0)
        
    if moisture is None:
        moisture_stress_comp = 0.5
    else:
        moisture_stress_comp = _bell_curve_stress(
            float(moisture),
            optimum=0.50,
            tolerance=0.20,
        )
        
    if temp_c is None:
        temp_stress_comp = 0.5
    else:
        temp_stress_comp = _bell_curve_stress(
            float(temp_c),
            optimum=24.0,
            tolerance=10.0,
        )
        
    proxy = soc_favour * 0.40 + (1.0 - moisture_stress_comp) * 0.35 + (1.0 - temp_stress_comp) * 0.25
    microbial_stress = _clamp(1.0 - proxy)

    raw = (
        ph_stress         * 0.25 +
        carbon_stress     * 0.20 +
        nitrogen_stress   * 0.15 +
        moisture_stress   * 0.15 +
        compaction_stress * 0.15 +
        microbial_stress  * 0.10
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 3 – Floral Diversity
# ──────────────────────────────────────────────────────────────────────────────

def score_floral_diversity(
    ndvi: dict[str, Any],
    gbif: dict[str, Any],
    zone_id: str = "",
) -> float:
    """
    Floral diversity stress (0–1).

    Sub-signals
    -----------
    ndvi_stress    (35% weight): stress when NDVI < 0.35 (sparse vegetation;
        calibrated from MODIS NDVI studies in Indian agricultural zones).
    flower_stress  (25% weight): stress when flowering coverage < 0.25.
    patch_stress   (20% weight): stress when patch diversity index < 0.50.
    species_stress (20% weight): inverse of species count normalised by
        SPECIES_COUNT_FLORAL_NORM (12 for most zones; configurable per zone
        via get_species_norm_for_zone to prevent ceiling effects in tropical
        high-biodiversity zones like Kerala).

    _NEUTRAL_STRESS (0.5) means data unavailable — not a healthy nor stressed signal.
    Zero species_count (0) is a legitimate value and is NOT replaced by a default.

    Inputs expected
    ---------------
    ndvi.ndvi                 : float | None  NDVI index (0–1).
    ndvi.flowering_coverage   : float | None  Fraction of flowering coverage.
    ndvi.patch_diversity      : float | None  Landscape patch diversity (0–1).
    gbif.species_count        : int | None    Unique pollinator species observed.
    zone_id                   : str           Used for per-zone species norm lookup.

    Calibration sources
    -------------------
    - MODIS NDVI Indian agricultural zone baseline (0.35 threshold)
    - GBIF India occurrence data 2020–2024 (12 species median for IGP)
    """
    ndvi_val      = ndvi.get("ndvi")
    evi_val       = ndvi.get("evi")
    flower_cov    = ndvi.get("flowering_coverage")
    patch_div     = ndvi.get("patch_diversity")
    species_count = gbif.get("species_count")  # 0 is valid real data

    floral_norm = get_species_norm_for_zone(zone_id, norm_key="floral")

    vegetation_index = ndvi_val
    if ndvi_val is not None and float(ndvi_val) >= 0.75 and evi_val is not None:
        vegetation_index = evi_val

    ndvi_stress    = _linear_stress(
        _SC["floral_ndvi_threshold"] - float(vegetation_index), 0.0, _SC["floral_ndvi_threshold"]
    ) if vegetation_index is not None else _NEUTRAL_STRESS

    flower_stress  = _linear_stress(
        _SC["floral_coverage_threshold"] - float(flower_cov), 0.0, _SC["floral_coverage_threshold"]
    ) if flower_cov is not None else _NEUTRAL_STRESS

    patch_stress   = _linear_stress(
        _SC["floral_patch_diversity_threshold"] - float(patch_div),
        0.0,
        _SC["floral_patch_diversity_threshold"],
    ) if patch_div is not None else _NEUTRAL_STRESS

    # species_count: 0 is a legitimate observation (no pollinators found).
    # If the value is None it means the data source failed — use neutral.
    if species_count is None:
        species_stress = _NEUTRAL_STRESS
    else:
        species_stress = _clamp(1.0 - float(species_count) / floral_norm)

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

    Sub-signals
    -----------
    visit_stress      (35% weight): stress when visitation_ratio < 0.75
        (IBRA/BeeWalk survey methodology threshold).
    decline_stress    (25% weight): proportional to 12-week decline rate,
        normalised by 0.55 (COLOSS winter loss survey: 55% decline = full stress).
    timing_stress     (20% weight): direct pass-through of
        pollination_timing_disruption (0–1 modelled or observed).
    flowering_stress  (15% weight): stress when flowering_success_rate < 0.65
        (FAO crop pollination guidelines for adequate fruit/seed set).
    volatility_stress  (5% weight): direct pass-through of recovery_volatility.

    _NEUTRAL_STRESS (0.5) when any value is None (source unavailable).
    Zero values (0.0 ratio, 0.0 decline) are legitimate and NOT replaced by defaults.

    Calibration sources
    -------------------
    - IBRA/BeeWalk survey methodology (visit ratio threshold)
    - COLOSS 2022 winter colony loss survey (decline normaliser 0.55)
    - FAO crop pollination guidelines (flowering success threshold 0.65)
    """
    visit_ratio         = visitation.get("visitation_ratio")
    decline_rate        = visitation.get("decline_rate_12w")
    timing_disruption   = visitation.get("pollination_timing_disruption")
    flowering_success   = visitation.get("flowering_success_rate")
    recovery_volatility = visitation.get("recovery_volatility")

    if visit_ratio is None:
        visit_stress = _NEUTRAL_STRESS
    else:
        visit_stress = _linear_stress(
            _SC["poll_visit_ratio_threshold"] - float(visit_ratio),
            0.0,
            _SC["poll_visit_ratio_threshold"],
        )

    if decline_rate is None:
        decline_stress = _NEUTRAL_STRESS
    else:
        decline_stress = _clamp(float(decline_rate) / _SC["poll_decline_normaliser"])

    timing_stress = _clamp(float(timing_disruption)) if timing_disruption is not None else _NEUTRAL_STRESS

    if flowering_success is None:
        flowering_stress = _NEUTRAL_STRESS
    else:
        flowering_stress = _linear_stress(
            _SC["poll_flowering_threshold"] - float(flowering_success),
            0.0,
            _SC["poll_flowering_threshold"],
        )

    volatility_stress = _clamp(float(recovery_volatility)) if recovery_volatility is not None else _NEUTRAL_STRESS

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

    Sub-signals
    -----------
    temp_stress       (30% weight): linear ramp; thresholds are latitude-dependent:
        tropical (|lat| < 25°): 8–20 °C std dev; temperate: 4–14 °C std dev.
        Based on ANOMALY_THRESHOLDS temp_variance_warning / _critical with Indian
        zone overrides for typical diurnal swing calibration.
    precip_stress     (30% weight): stress when total 30-day precip < 30 mm
        (deficit from typical monsoon baseline; ANOMALY_THRESHOLDS rainfall_deficit).
    drought_stress    (25% weight): sigmoid centred at 0.55 (FAO aridity index
        semi-arid classification; ETP/precipitation ratio).
    precip_var_stress (15% weight): linear, captures intra-season rainfall
        variability which disrupts flowering phenology.

    _NEUTRAL_STRESS (0.5) when any value is None (data unavailable).

    Calibration sources
    -------------------
    - ANOMALY_THRESHOLDS (this module, zone-aware)
    - FAO aridity index (drought sigmoid midpoint 0.55)
    - IMD historical monsoon data for Indian zone lat thresholds
    """
    temp_std     = climate.get("temp_std_c")
    total_precip = climate.get("total_precipitation_mm")
    precip_std   = climate.get("precip_std_mm")
    drought_idx  = climate.get("drought_index")
    wind_kmh     = climate.get("avg_windspeed_kmh")

    tropical_lat = _SC["tropical_lat_threshold"]

    if temp_std is None:
        temp_stress = _NEUTRAL_STRESS
    elif abs(lat) < tropical_lat:
        temp_stress = _linear_stress(
            float(temp_std),
            _SC["temp_std_tropical_lo"],
            _SC["temp_std_tropical_hi"],
        )
    else:
        temp_stress = _linear_stress(
            float(temp_std),
            _SC["temp_std_temperate_lo"],
            _SC["temp_std_temperate_hi"],
        )

    precip_stress = (
        _linear_stress(30.0 - float(total_precip), _SC["precip_deficit_lo_ok"], _SC["precip_deficit_hi_stress"])
        if total_precip is not None else _NEUTRAL_STRESS
    )

    # Sigmoid drought stress — None means data unavailable, use neutral
    if drought_idx is None:
        drought_stress = _NEUTRAL_STRESS
    else:
        drought_stress = _clamp(_sigmoid_stress(
            float(drought_idx),
            midpoint=_SC["drought_sigmoid_midpoint"],
            steepness=_SC["drought_sigmoid_steepness"],
        ))

    # 2.5: Wind stress — avg_windspeed_kmh is fetched by Open-Meteo and stored
    # in the climate dict but was previously discarded.  Linear ramp from
    # wind_stress_lo_kmh (15 km/h, foraging becomes erratic) to
    # wind_stress_hi_kmh (25 km/h, complete flight cessation).
    # Weight: 15%, replacing precip_var_stress (dropped to 0%) because
    # precipitation variability is already captured by the deficit signal.
    wind_stress = (
        _linear_stress(
            float(wind_kmh),
            _SC["wind_stress_lo_kmh"],
            _SC["wind_stress_hi_kmh"],
        )
        if wind_kmh is not None else _NEUTRAL_STRESS
    )

    raw = (
        temp_stress   * 0.30 +
        precip_stress * 0.30 +
        drought_stress * 0.25 +
        wind_stress   * 0.15
    )
    return _clamp(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Factor 5 – Nesting Availability
# ──────────────────────────────────────────────────────────────────────────────

def score_nesting_availability(ndvi: dict[str, Any], water: dict[str, Any] | None = None) -> float:
    """
    Nesting availability stress (0–1).

    Sub-signals
    -----------
    bare_stress  (30% weight): optimal bare-soil fraction is 5–30%; too low
        means dense canopy with no ground-nesting sites, too high means
        disturbed or arid landscape with few nest resources.
        Threshold 30% matches ANOMALY_THRESHOLDS bare_soil_warning.
    hedge_stress (25% weight): stress when hedgerow density < 0.30 (30% linear
        hedge cover per hectare).  Threshold from UK agri-environment scheme
        pollinator metrics (Woodcock et al. 2016).
    dw_stress    (20% weight): stress when dead-wood index < 0.20 (cavity-nesting
        bee habitat; threshold from Stokland et al. 2012 deadwood review).
    dist_stress  (25% weight): direct pass-through of disturbance_score (0–1).
        Matches ANOMALY_THRESHOLDS disturbance_warning / _critical.

    _NEUTRAL_STRESS (0.5) when any value is None (source unavailable).

    Calibration sources
    -------------------
    - ANOMALY_THRESHOLDS (bare soil, disturbance)
    - Woodcock et al. 2016 (hedgerow density)
    - Stokland et al. 2012 (dead wood index)
    """
    bare_soil   = ndvi.get("bare_soil_fraction")
    hedgerow    = ndvi.get("hedgerow_density")
    dead_wood   = ndvi.get("dead_wood_index")
    disturbance = ndvi.get("disturbance_score")

    hi = _SC["nesting_bare_soil_hi_threshold"]
    lo = _SC["nesting_bare_soil_lo_threshold"]

    if bare_soil is None:
        bare_stress = _NEUTRAL_STRESS
    elif float(bare_soil) > hi:
        bare_stress = _linear_stress(float(bare_soil) - hi, 0.0, 0.45)
    else:
        bare_stress = _linear_stress(lo - float(bare_soil), 0.0, lo)

    hedge_norm = _SC["nesting_hedge_optimum"]
    hedge_stress = (
        _linear_stress(hedge_norm - float(hedgerow), 0.0, hedge_norm)
        if hedgerow is not None else _NEUTRAL_STRESS
    )

    dw_norm = _SC["nesting_deadwood_optimum"]
    dw_stress = (
        _linear_stress(dw_norm - float(dead_wood), 0.0, dw_norm)
        if dead_wood is not None else _NEUTRAL_STRESS
    )

    dist_stress = _clamp(float(disturbance)) if disturbance is not None else _NEUTRAL_STRESS

    # 2.3: Water proximity — pollinators need water within foraging range
    if water is not None and water.get("water_proximity_score") is not None:
        water_stress = _clamp(1.0 - float(water["water_proximity_score"]))
    else:
        water_stress = _NEUTRAL_STRESS

    raw = (
        bare_stress  * 0.30 +
        hedge_stress * 0.25 +
        dw_stress    * 0.20 +
        dist_stress  * 0.10 +
        water_stress * 0.15
    )
    return _clamp(raw)

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


# ────────────────────────────────────────────────────────────────────────────────
# Inter-factor interaction terms (6.2)
# ────────────────────────────────────────────────────────────────────────────────

def _interaction_terms(factor_scores: dict[str, float]) -> float:
    """
    Compute a synergistic penalty to add to overall_stress when two stressors
    are simultaneously above INTERACTION_STRESS_THRESHOLD.

    Returns the total additive penalty (0.0 when no pairs activate).
    The caller is responsible for clamping overall_stress to [0, 1] after
    adding the result.
    """
    total_penalty = 0.0
    for (fa, fb), penalty in INTERACTION_PENALTIES.items():
        sa = float(factor_scores.get(fa, 0.0))
        sb = float(factor_scores.get(fb, 0.0))
        if sa >= INTERACTION_STRESS_THRESHOLD and sb >= INTERACTION_STRESS_THRESHOLD:
            total_penalty += penalty
    return total_penalty


# ──────────────────────────────────────────────────────────────────────────────
# Crop risk
# ──────────────────────────────────────────────────────────────────────────────

def compute_crop_risk_details(
    overall_stress: float,
    zone_id: str = "",
    geo_profile: dict | None = None,
) -> dict[str, dict[str, Any]]:
    """Return crop risk labels plus optional monetised value-at-risk details."""
    risks: dict[str, Any] = {}
    # Derive state code from zone_id prefix (e.g. "IN_KA_01" → "IN_KA")
    state = "_".join(zone_id.split("_")[:2]) if zone_id else None
    for crop, dep in get_crop_dependency_for_zone(zone_id, geo_profile).items():
        impact = _clamp(dep * overall_stress)
        label = _label_from_bands(impact, CROP_RISK_LABELS)
        entry: dict[str, Any] = {"risk_label": label}
        # 2.4: Value at risk in INR per hectare
        try:
            from agmarknet import compute_value_at_risk
            var = compute_value_at_risk(crop, dep, overall_stress, state)
            if var is not None:
                entry["value_at_risk_inr"] = var
        except Exception:
            pass
        risks[crop] = entry
    return risks



def _anomaly_stress_floor(anomalies: list[dict[str, Any]]) -> float:
    """
    Compute a minimum stress floor from anomaly severity, driven by the number
    of *distinct critical factors* (not raw anomaly count).

    Floor table
    -----------
    distinct critical factors | base floor
    ─────────────────────────┼───────────
    0                         | 0.00
    1                         | 0.34
    2                         | 0.45
    ≥3                        | 0.52

    An additive warning bonus of 0.02 per WARNING anomaly (max +0.10) is then
    applied on top.  Using distinct *factors* prevents a single noisy source
    (e.g., three pesticide anomalies all tagged to the same factor) from
    inflating the floor to the three-factor level.

    Examples
    --------
    - 5 CRITICAL anomalies all on "pesticide_exposure" → 1 distinct factor → 0.34
    - 2 CRITICAL anomalies on "soil_fertility" + "climate_variability" → 0.45
    - 3 CRITICAL anomalies on 3 different factors → 0.52
    """
    warning_factors = {
        item.get("factor")
        for item in anomalies
        if item.get("severity") == "WARNING"
    }
    critical_factors = {
        item.get("factor")
        for item in anomalies
        if item.get("severity") == "CRITICAL"
    }

    num_critical = len(critical_factors)

    if num_critical >= 3:
        floor = 0.52
    elif num_critical == 2:
        floor = 0.45
    elif num_critical == 1:
        floor = 0.34
    else:
        floor = 0.0

    # Fix 1.2: use distinct warning factor count (not total anomaly count)
    floor += min(0.10, len(warning_factors) * 0.02)
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
    scores["activity_score"] = (1.0 - adjusted_stress) * 100
    scores["activity_label"] = _label_from_bands(scores["activity_score"], ACTIVITY_SCORE_LABELS)
    scores["pollination_stress_index"] = _label_from_bands(adjusted_stress, STRESS_INDEX_THRESHOLDS)
    crop_risk_details = compute_crop_risk_details(adjusted_stress, zone_id=zone_id, geo_profile=geo_profile)
    scores["crop_risk"] = {crop: detail["risk_label"] for crop, detail in crop_risk_details.items()}
    scores["crop_risk_details"] = crop_risk_details
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

def compute_crop_weighted_stress(
    factor_scores: dict[str, float],
    crop_dependency: dict[str, float],
) -> float | None:
    """
    Crop-weighted stress index (6.4): instead of using global factor weights,
    weight factors by their affinity to the zone's actual crop mix.
    """
    total_stress = 0.0
    total_weight = 0.0
    
    for crop, dependency in crop_dependency.items():
        if crop in CROP_FACTOR_AFFINITY:
            affinity = CROP_FACTOR_AFFINITY[crop]
            crop_stress = sum(factor_scores.get(f, 0.0) * w for f, w in affinity.items())
            total_stress += crop_stress * dependency
            total_weight += dependency
            
    if total_weight > 0:
        return _clamp(total_stress / total_weight)
    return None


def compute_all_scores(raw_data: dict[str, Any], zone_id: str = "") -> dict[str, Any]:
    climate    = raw_data.get("climate", {})
    nasa       = raw_data.get("nasa", {})
    soil       = raw_data.get("soil", {})
    ndvi       = raw_data.get("ndvi", {})
    gbif       = raw_data.get("gbif", {})
    pesticide  = raw_data.get("pesticide", {})
    visitation = raw_data.get("visitation", {})
    lat        = raw_data.get("_meta", {}).get("lat", 0.0)
    geo_profile = raw_data.get("_meta", {}).get("geo_profile", None)

    # Compute at full float precision — rounding happens at the API serialisation
    # layer only (in _build_output / the HTTP response), not here.
    f_pest        = score_pesticide_exposure(pesticide)
    f_soil = score_soil_fertility(
        raw_data.get("soil", {}),
        raw_data.get("nasa", {}),
        raw_data.get("climate", {}),
    )
    f_floral      = score_floral_diversity(ndvi, gbif, zone_id=zone_id)
    f_climate     = score_climate_variability(climate, lat=lat)
    f_nesting     = score_nesting_availability(ndvi, raw_data.get("water", {}))
    f_pollination = score_pollination_factor(visitation)

    # Store raw float values — _r2() applied only in API serialisation layer.
    factor_scores = {
        "pesticide_exposure":   f_pest,
        "soil_fertility":       f_soil,
        "floral_diversity":     f_floral,
        "climate_variability":  f_climate,
        "nesting_availability": f_nesting,
        "pollination_factor":   f_pollination,
    }

    # Fix 6: use per-zone weights from zone_weights.yaml if available
    effective_weights = get_factor_weights_for_zone(zone_id, geo_profile)

    overall_stress = _clamp(sum(
        factor_scores[k] * effective_weights[k] for k in effective_weights
    ))

    # 6.2: Add synergistic interaction penalty when paired stressors both exceed
    # the activation threshold.  Penalty is conservative and capped at the sum
    # of all defined penalties (~0.17) to prevent score distortion.
    interaction_penalty = _interaction_terms(factor_scores)
    overall_stress = _clamp(overall_stress + interaction_penalty)
    factor_scores["interaction_penalty"] = round(interaction_penalty, 4)

    activity_score = (1.0 - overall_stress) * 100
    activity_label = _label_from_bands(_r2(activity_score), ACTIVITY_SCORE_LABELS)

    contribution_scores = {
        k: factor_scores[k] * effective_weights[k] * 100
        for k in effective_weights  # interaction_penalty is not in weights; skip it
    }

    habitat_score = compute_habitat_suitability(f_floral, f_nesting, f_soil)
    stress_label  = _label_from_bands(overall_stress, STRESS_INDEX_THRESHOLDS)

    crop_dependency = get_crop_dependency_for_zone(zone_id, geo_profile)
    crop_risk_details = compute_crop_risk_details(overall_stress, zone_id=zone_id, geo_profile=geo_profile)
    crop_risk = {crop: detail["risk_label"] for crop, detail in crop_risk_details.items()}
    crop_weighted_stress = compute_crop_weighted_stress(factor_scores, crop_dependency)

    return {
        "factor_scores":             factor_scores,   # raw floats, rounded at API layer
        "overall_stress":            overall_stress,  # raw float
        "crop_weighted_stress":      crop_weighted_stress, # raw float
        "activity_score":            activity_score,  # raw float
        "activity_label":            activity_label,
        "habitat_suitability_score": habitat_score,
        "pollination_stress_index":  stress_label,
        "crop_risk":                 crop_risk,
        "crop_risk_details":         crop_risk_details,
        "crop_dependency":           crop_dependency,
        "crop_dependency_basis":     "coarse literature-informed estimates, not field-calibrated measurements",
        "factor_weights":            effective_weights,  # Fix 6: zone-specific
        "contribution_scores":       contribution_scores,
    }
