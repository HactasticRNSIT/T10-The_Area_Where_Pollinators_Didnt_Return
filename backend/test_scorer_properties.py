"""
test_scorer_properties.py — Property-based tests for scorer.py math invariants.

These tests replace the previous stub that called a nonexistent function signature.
They use Hypothesis to sweep extreme-but-realistic inputs over every scoring function
and assert the bounds that comprehensive_walkthrough.md claims are "proven":
  - All per-factor stress functions → [0.0, 1.0]
  - activity_score              → [0.0, 100.0]
  - overall_stress              → [0.0, 1.0]
  - habitat_suitability_score   → [0.0, 100.0]

Run with:  pytest backend/test_scorer_properties.py -x -q
"""

import math
import pytest
from hypothesis import given, settings, strategies as st, assume

from scorer import (
    _sigmoid_stress,
    _bell_curve_stress,
    score_pesticide_exposure,
    score_soil_fertility,
    score_floral_diversity,
    score_climate_variability,
    score_nesting_availability,
    score_pollination_factor,
    compute_all_scores,
)


# ──────────────────────────────────────────────────────────────────────────────
# Strategy helpers
# ──────────────────────────────────────────────────────────────────────────────

# Finite floats, including very large and very small values, but no NaN/Inf.
_FLOAT = st.floats(allow_nan=False, allow_infinity=False)

# The unit interval [0, 1], used for fractional inputs.
_UNIT = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Floats that may be None (simulating a missing / unavailable data source).
def _nullable(strategy):
    return st.one_of(st.none(), strategy)


# ──────────────────────────────────────────────────────────────────────────────
# Low-level math primitives
# ──────────────────────────────────────────────────────────────────────────────

@given(
    value=_FLOAT,
    midpoint=_FLOAT,
    steepness=st.floats(min_value=0.001, max_value=20.0,
                        allow_nan=False, allow_infinity=False),
)
def test_sigmoid_stress_bounds(value, midpoint, steepness):
    """_sigmoid_stress always returns a value in [0, 1]."""
    # Guard against overflow in math.exp for extreme |steepness * (value - midpoint)|
    assume(abs(steepness * (value - midpoint)) < 700)
    result = _sigmoid_stress(value, midpoint, steepness)
    assert 0.0 <= result <= 1.0, f"sigmoid out of [0,1]: {result}"


@given(
    value=_FLOAT,
    optimum=_FLOAT,
    tolerance=st.floats(min_value=0.001, max_value=1e6,
                        allow_nan=False, allow_infinity=False),
)
def test_bell_curve_stress_bounds(value, optimum, tolerance):
    """_bell_curve_stress always returns a value in [0, 1]."""
    result = _bell_curve_stress(value, optimum, tolerance)
    assert 0.0 <= result <= 1.0, f"bell_curve out of [0,1]: {result}"


@given(
    value=_FLOAT,
    optimum=_FLOAT,
    tolerance=st.floats(min_value=0.001, max_value=1e6,
                        allow_nan=False, allow_infinity=False),
)
def test_bell_curve_stress_zero_at_optimum(value, optimum, tolerance):
    """At the optimum point the stress is exactly 0.0."""
    result = _bell_curve_stress(optimum, optimum, tolerance)
    assert result == 0.0, f"bell_curve at optimum not 0: {result}"


# ──────────────────────────────────────────────────────────────────────────────
# score_pesticide_exposure — dict[str, Any] → [0, 1]
# ──────────────────────────────────────────────────────────────────────────────

@given(
    usage_ppm=_nullable(st.floats(min_value=-10.0, max_value=500.0,
                                   allow_nan=False, allow_infinity=False)),
    apps=_nullable(st.floats(min_value=0.0, max_value=50.0,
                              allow_nan=False, allow_infinity=False)),
    days=_nullable(st.floats(min_value=0.0, max_value=365.0,
                              allow_nan=False, allow_infinity=False)),
    t_mult=_nullable(st.floats(min_value=0.0, max_value=5.0,
                                allow_nan=False, allow_infinity=False)),
)
def test_score_pesticide_exposure_bounds(usage_ppm, apps, days, t_mult):
    """score_pesticide_exposure always returns a value in [0, 1]."""
    pesticide = {
        "usage_ppm": usage_ppm,
        "applications_per_month": apps,
        "days_since_last_application": days,
        "toxicity_multiplier": t_mult,
    }
    result = score_pesticide_exposure(pesticide)
    assert 0.0 <= result <= 1.0, f"pesticide stress out of [0,1]: {result}"


def test_score_pesticide_exposure_empty_dict():
    """Empty pesticide dict (all None) returns a finite value in [0, 1]."""
    result = score_pesticide_exposure({})
    assert 0.0 <= result <= 1.0


def test_score_pesticide_exposure_zero_is_lower_than_high():
    """Zero pesticide should produce strictly lower stress than intensive use."""
    low = score_pesticide_exposure({
        "usage_ppm": 0.0,
        "applications_per_month": 0,
        "days_since_last_application": 60,
        "toxicity_multiplier": 0.5,
    })
    high = score_pesticide_exposure({
        "usage_ppm": 50.0,
        "applications_per_month": 12,
        "days_since_last_application": 0,
        "toxicity_multiplier": 1.8,
    })
    assert low < high, f"Expected low({low}) < high({high})"


# ──────────────────────────────────────────────────────────────────────────────
# score_soil_fertility — dicts → [0, 1]
# ──────────────────────────────────────────────────────────────────────────────

@given(
    ph=_nullable(st.floats(min_value=0.0, max_value=14.0,
                            allow_nan=False, allow_infinity=False)),
    soc=_nullable(st.floats(min_value=0.0, max_value=100.0,
                             allow_nan=False, allow_infinity=False)),
    nitrogen=_nullable(st.floats(min_value=0.0, max_value=10.0,
                                  allow_nan=False, allow_infinity=False)),
    compaction=_nullable(_UNIT),
    root_zone=_nullable(_UNIT),
    temp=_nullable(st.floats(min_value=-30.0, max_value=60.0,
                              allow_nan=False, allow_infinity=False)),
)
def test_score_soil_fertility_bounds(ph, soc, nitrogen, compaction, root_zone, temp):
    """score_soil_fertility always returns a value in [0, 1]."""
    soil = {
        "ph": ph,
        "organic_carbon_g_per_kg": soc,
        "nitrogen_g_per_kg": nitrogen,
        "compaction_index": compaction,
    }
    nasa = {"root_zone_wetness": root_zone}
    climate = {"temp_mean_c": temp}
    result = score_soil_fertility(soil, nasa, climate)
    assert 0.0 <= result <= 1.0, f"soil stress out of [0,1]: {result}"


def test_score_soil_fertility_empty_dicts():
    """All-None inputs (empty dicts) returns neutral value in [0, 1]."""
    result = score_soil_fertility({}, {}, {})
    assert 0.0 <= result <= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# score_floral_diversity — dicts → [0, 1]
# ──────────────────────────────────────────────────────────────────────────────

@given(
    ndvi_val=_nullable(_UNIT),
    evi_val=_nullable(_UNIT),
    flower_cov=_nullable(_UNIT),
    patch_div=_nullable(_UNIT),
    species_count=_nullable(st.integers(min_value=0, max_value=500)),
    zone_id=st.sampled_from(["IN_KA_01", "IN_KL_01", "IN_RJ_01", ""]),
)
def test_score_floral_diversity_bounds(ndvi_val, evi_val, flower_cov, patch_div, species_count, zone_id):
    """score_floral_diversity always returns a value in [0, 1]."""
    ndvi = {
        "ndvi": ndvi_val,
        "evi": evi_val,
        "flowering_coverage": flower_cov,
        "patch_diversity": patch_div,
    }
    gbif = {"species_count": species_count}
    result = score_floral_diversity(ndvi, gbif, zone_id=zone_id)
    assert 0.0 <= result <= 1.0, f"floral diversity stress out of [0,1]: {result}"


# ──────────────────────────────────────────────────────────────────────────────
# score_climate_variability — dict → [0, 1]
# ──────────────────────────────────────────────────────────────────────────────

@given(
    temp_std=_nullable(st.floats(min_value=0.0, max_value=30.0,
                                  allow_nan=False, allow_infinity=False)),
    total_precip=_nullable(st.floats(min_value=0.0, max_value=1000.0,
                                      allow_nan=False, allow_infinity=False)),
    precip_std=_nullable(st.floats(min_value=0.0, max_value=100.0,
                                    allow_nan=False, allow_infinity=False)),
    drought_idx=_nullable(_UNIT),
    wind=_nullable(st.floats(min_value=0.0, max_value=150.0,
                              allow_nan=False, allow_infinity=False)),
    lat=st.floats(min_value=-90.0, max_value=90.0,
                  allow_nan=False, allow_infinity=False),
)
def test_score_climate_variability_bounds(temp_std, total_precip, precip_std, drought_idx, wind, lat):
    """score_climate_variability always returns a value in [0, 1]."""
    climate = {
        "temp_std_c": temp_std,
        "total_precipitation_mm": total_precip,
        "precip_std_mm": precip_std,
        "drought_index": drought_idx,
        "avg_windspeed_kmh": wind,
    }
    result = score_climate_variability(climate, lat=lat)
    assert 0.0 <= result <= 1.0, f"climate variability stress out of [0,1]: {result}"


# ──────────────────────────────────────────────────────────────────────────────
# score_nesting_availability — dicts → [0, 1]
# ──────────────────────────────────────────────────────────────────────────────

@given(
    bare_soil=_nullable(_UNIT),
    hedgerow=_nullable(_UNIT),
    dead_wood=_nullable(_UNIT),
    disturbance=_nullable(_UNIT),
    water_score=_nullable(_UNIT),
)
def test_score_nesting_availability_bounds(bare_soil, hedgerow, dead_wood, disturbance, water_score):
    """score_nesting_availability always returns a value in [0, 1]."""
    ndvi = {
        "bare_soil_fraction": bare_soil,
        "hedgerow_density": hedgerow,
        "dead_wood_index": dead_wood,
        "disturbance_score": disturbance,
    }
    water = {"water_proximity_score": water_score}
    result = score_nesting_availability(ndvi, water)
    assert 0.0 <= result <= 1.0, f"nesting stress out of [0,1]: {result}"


# ──────────────────────────────────────────────────────────────────────────────
# score_pollination_factor — dict → [0, 1]
# ──────────────────────────────────────────────────────────────────────────────

@given(
    visit_ratio=_nullable(st.floats(min_value=0.0, max_value=5.0,
                                     allow_nan=False, allow_infinity=False)),
    decline=_nullable(_UNIT),
    timing=_nullable(_UNIT),
    flowering_success=_nullable(_UNIT),
    volatility=_nullable(_UNIT),
)
def test_score_pollination_factor_bounds(visit_ratio, decline, timing, flowering_success, volatility):
    """score_pollination_factor always returns a value in [0, 1]."""
    visitation = {
        "visitation_ratio": visit_ratio,
        "decline_rate_12w": decline,
        "pollination_timing_disruption": timing,
        "flowering_success_rate": flowering_success,
        "recovery_volatility": volatility,
    }
    result = score_pollination_factor(visitation)
    assert 0.0 <= result <= 1.0, f"pollination factor stress out of [0,1]: {result}"


# ──────────────────────────────────────────────────────────────────────────────
# compute_all_scores — end-to-end bounds
# ──────────────────────────────────────────────────────────────────────────────

# Build a representative raw_data bundle from individually-fuzzed sub-dicts.
_CLIMATE_ST = st.fixed_dictionaries({
    "temp_std_c":             _nullable(st.floats(0.0, 25.0, allow_nan=False, allow_infinity=False)),
    "total_precipitation_mm": _nullable(st.floats(0.0, 800.0, allow_nan=False, allow_infinity=False)),
    "precip_std_mm":          _nullable(st.floats(0.0, 80.0, allow_nan=False, allow_infinity=False)),
    "drought_index":          _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "avg_windspeed_kmh":      _nullable(st.floats(0.0, 120.0, allow_nan=False, allow_infinity=False)),
    "temp_mean_c":            _nullable(st.floats(-20.0, 55.0, allow_nan=False, allow_infinity=False)),
})

_NASA_ST = st.fixed_dictionaries({
    "root_zone_wetness": _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
})

_SOIL_ST = st.fixed_dictionaries({
    "ph":                        _nullable(st.floats(0.0, 14.0, allow_nan=False, allow_infinity=False)),
    "organic_carbon_g_per_kg":   _nullable(st.floats(0.0, 60.0, allow_nan=False, allow_infinity=False)),
    "nitrogen_g_per_kg":         _nullable(st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False)),
    "compaction_index":          _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
})

_NDVI_ST = st.fixed_dictionaries({
    "ndvi":               _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "evi":                _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "flowering_coverage": _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "patch_diversity":    _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "bare_soil_fraction": _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "hedgerow_density":   _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "dead_wood_index":    _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "disturbance_score":  _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
})

_GBIF_ST = st.fixed_dictionaries({
    "species_count": _nullable(st.integers(min_value=0, max_value=200)),
})

_PESTICIDE_ST = st.fixed_dictionaries({
    "usage_ppm":                    _nullable(st.floats(0.0, 200.0, allow_nan=False, allow_infinity=False)),
    "applications_per_month":       _nullable(st.floats(0.0, 30.0, allow_nan=False, allow_infinity=False)),
    "days_since_last_application":  _nullable(st.floats(0.0, 365.0, allow_nan=False, allow_infinity=False)),
    "toxicity_multiplier":          _nullable(st.floats(0.0, 3.0, allow_nan=False, allow_infinity=False)),
})

_VISITATION_ST = st.fixed_dictionaries({
    "visitation_ratio":              _nullable(st.floats(0.0, 5.0, allow_nan=False, allow_infinity=False)),
    "decline_rate_12w":              _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "pollination_timing_disruption": _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "flowering_success_rate":        _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
    "recovery_volatility":           _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
})

_WATER_ST = st.fixed_dictionaries({
    "water_proximity_score": _nullable(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)),
})


@given(
    climate=_CLIMATE_ST,
    nasa=_NASA_ST,
    soil=_SOIL_ST,
    ndvi=_NDVI_ST,
    gbif=_GBIF_ST,
    pesticide=_PESTICIDE_ST,
    visitation=_VISITATION_ST,
    water=_WATER_ST,
    zone_id=st.sampled_from(["IN_KA_01", "IN_KL_01", "IN_RJ_01", "IN_HP_01", ""]),
)
@settings(max_examples=200)
def test_compute_all_scores_output_bounds(
    climate, nasa, soil, ndvi, gbif, pesticide, visitation, water, zone_id,
):
    """
    Property test: compute_all_scores always emits:
      - overall_stress       ∈ [0.0, 1.0]
      - activity_score       ∈ [0.0, 100.0]
      - habitat_suitability  ∈ [0.0, 100.0]
      - every factor_score   ∈ [0.0, 1.0]

    This is the bound that comprehensive_walkthrough.md claims is "mathematically proven".
    """
    raw_data = {
        "climate":   climate,
        "nasa":      nasa,
        "soil":      soil,
        "ndvi":      ndvi,
        "gbif":      gbif,
        "pesticide": pesticide,
        "visitation": visitation,
        "water":     water,
    }
    scores = compute_all_scores(raw_data, zone_id=zone_id)

    overall_stress = scores["overall_stress"]
    activity_score = scores["activity_score"]
    habitat_score  = scores["habitat_suitability_score"]

    assert 0.0 <= overall_stress <= 1.0, (
        f"overall_stress out of [0,1]: {overall_stress}"
    )
    assert 0.0 <= activity_score <= 100.0, (
        f"activity_score out of [0,100]: {activity_score}"
    )
    assert 0.0 <= habitat_score <= 100.0, (
        f"habitat_suitability_score out of [0,100]: {habitat_score}"
    )

    # All individual factor scores must also be bounded.
    for factor, value in scores["factor_scores"].items():
        if factor == "interaction_penalty":
            # Additive penalty — still bounded by the sum of all defined penalties,
            # which is at most ~0.17.  Just assert it's finite and non-negative.
            assert 0.0 <= value <= 1.0, f"interaction_penalty out of [0,1]: {value}"
        else:
            assert 0.0 <= value <= 1.0, (
                f"factor_scores[{factor!r}] out of [0,1]: {value}"
            )


def test_compute_all_scores_empty_bundle():
    """compute_all_scores with all-empty sub-dicts returns a valid structure."""
    scores = compute_all_scores({}, zone_id="")
    assert 0.0 <= scores["overall_stress"] <= 1.0
    assert 0.0 <= scores["activity_score"] <= 100.0
    assert isinstance(scores["activity_label"], str)
