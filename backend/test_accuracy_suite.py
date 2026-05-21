import pytest
import math
from scorer import (
    _sigmoid_stress,
    _linear_stress,
    _clamp,
    score_pesticide_exposure,
    score_soil_fertility,
    compute_all_scores
)
from mock_data import get_full_mock_bundle

# ──────────────────────────────────────────────────────────────────────────────
# 1. Math Helper Accuracy
# ──────────────────────────────────────────────────────────────────────────────

def test_clamp():
    assert _clamp(-0.5) == 0.0
    assert _clamp(1.5) == 1.0
    assert _clamp(0.5) == 0.5

def test_linear_stress():
    # value, lo_ok, hi_stress
    assert _linear_stress(2.0, 5.0, 10.0) == 0.0  # below ok threshold -> 0 stress
    assert _linear_stress(12.0, 5.0, 10.0) == 1.0 # above hi threshold -> 1 stress
    assert _linear_stress(7.5, 5.0, 10.0) == 0.5  # exactly middle -> 0.5 stress

def test_sigmoid_stress():
    # Midpoint should be exactly 0.5
    assert _sigmoid_stress(10.0, midpoint=10.0, steepness=1.0) == 0.5
    
    # Far below midpoint -> approaches 0
    val_low = _sigmoid_stress(0.0, midpoint=10.0, steepness=1.0)
    assert 0.0 <= val_low < 0.01
    
    # Far above midpoint -> approaches 1
    val_high = _sigmoid_stress(20.0, midpoint=10.0, steepness=1.0)
    assert 0.99 < val_high <= 1.0

# ──────────────────────────────────────────────────────────────────────────────
# 2. Factor Scoring Accuracy (Testing Fix 5 Sigmoids)
# ──────────────────────────────────────────────────────────────────────────────

def test_pesticide_exposure_accuracy():
    """Verify pesticide scoring translates ppm concentrations to stress correctly via sigmoid."""
    # Near zero ppm
    low_stress = score_pesticide_exposure({
        "usage_ppm": 0.0,
        "applications_per_month": 0,
        "days_since_last_application": 30,
        "toxicity_multiplier": 1.0
    })
    
    # High ppm, high frequency, recent application
    high_stress = score_pesticide_exposure({
        "usage_ppm": 20.0,
        "applications_per_month": 8,
        "days_since_last_application": 0,
        "toxicity_multiplier": 1.0
    })
    
    # Mid ppm (10)
    mid_stress = score_pesticide_exposure({
        "usage_ppm": 10.0,
        "applications_per_month": 4,
        "days_since_last_application": 15,
        "toxicity_multiplier": 1.0
    })

    assert low_stress < 0.1, f"Expected low stress, got {low_stress}"
    assert high_stress > 0.9, f"Expected high stress, got {high_stress}"
    assert 0.4 < mid_stress < 0.6, f"Expected mid stress, got {mid_stress}"

def test_soil_fertility_ph_accuracy():
    """Verify pH is scored symmetrically around 6.5 optimum."""
    nasa_mock = {"root_zone_wetness": 0.50}
    
    def get_ph_stress(ph_val):
        # We isolate pH by setting other factors to optimal
        return score_soil_fertility({
            "ph": ph_val,
            "organic_carbon_g_per_kg": 2.0,
            "nitrogen_g_per_kg": 1.5,
            "compaction_index": 0.0
        }, nasa_mock)

    optimum = get_ph_stress(6.5)
    low_warn = get_ph_stress(5.5)
    low_crit = get_ph_stress(5.0)
    high_warn = get_ph_stress(7.5)
    high_crit = get_ph_stress(8.0)

    # 6.5 should be the lowest possible stress
    assert optimum < low_warn
    assert optimum < high_warn
    
    # Stress should increase as we move away from 6.5
    assert low_warn < low_crit
    assert high_warn < high_crit
    
    # Check bounds
    assert 0.0 <= optimum <= 1.0
    assert 0.0 <= low_crit <= 1.0

# ──────────────────────────────────────────────────────────────────────────────
# 3. Overall Scoring Constraints & Data Range Validity
# ──────────────────────────────────────────────────────────────────────────────

def test_compute_all_scores_boundaries():
    """Test that `compute_all_scores` produces outputs bounded correctly."""
    # Use the full mock bundle which simulates an entire location's data
    raw_data = get_full_mock_bundle(12.97, 77.59)
    raw_data["_meta"] = {"lat": 12.97, "lon": 77.59, "zone_id": "IN_KA"}
    raw_data["nasa"] = {"source": "mock_nasa_power", "root_zone_wetness": 0.45}
    
    scores = compute_all_scores(raw_data, zone_id="IN_KA")
    
    # Activity score must be 0-100
    assert 0.0 <= scores["activity_score"] <= 100.0
    
    # Overall stress must be 0-1
    assert 0.0 <= scores["overall_stress"] <= 1.0
    
    # Habitat suitability must be 0-100
    assert 0.0 <= scores["habitat_suitability_score"] <= 100.0
    
    # Factor scores must be 0-1
    for factor, value in scores["factor_scores"].items():
        assert 0.0 <= value <= 1.0, f"Factor {factor} out of bounds: {value}"
        
    # Valid labels
    valid_activity_labels = ["Healthy", "Moderate", "Stressed", "Critical", "Collapse Risk"]
    assert scores["activity_label"] in valid_activity_labels
    
    valid_stress_labels = ["Low", "Medium", "High", "Severe"]
    assert scores["pollination_stress_index"] in valid_stress_labels
