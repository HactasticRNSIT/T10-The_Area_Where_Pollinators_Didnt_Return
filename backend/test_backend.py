import pytest
from scorer import score_pesticide_exposure, compute_all_scores
from anomaly_detector import detect_anomalies, has_ai_trigger_anomaly
from config import ACTIVITY_SCORE_LABELS
from mock_data import get_full_mock_bundle

# ──────────────────────────────────────────────────────────────────────────────
# Test Scorer
# ──────────────────────────────────────────────────────────────────────────────
def test_score_pesticide_exposure():
    # High pesticide usage should result in high stress
    pesticide_data_high = {
        "usage_ppm": 20.0,
        "applications_per_month": 8,
        "days_since_last_application": 1,
        "pesticide_type": "neonicotinoid",
        "toxicity_multiplier": 1.40
    }
    stress_high = score_pesticide_exposure(pesticide_data_high)
    assert stress_high > 0.8, f"Expected high stress, got {stress_high}"

    # Low pesticide usage should result in low stress
    pesticide_data_low = {
        "usage_ppm": 0.0,
        "applications_per_month": 0,
        "days_since_last_application": 40,
        "pesticide_type": "biopesticide",
        "toxicity_multiplier": 0.60
    }
    stress_low = score_pesticide_exposure(pesticide_data_low)
    assert stress_low < 0.2, f"Expected low stress, got {stress_low}"

def test_compute_all_scores():
    # Use mock data for a full run
    lat, lon = 52.2053, 0.1218
    raw_bundle = get_full_mock_bundle(lat, lon)
    # Add fake climate and nasa data that would normally come from APIs
    raw_bundle["climate"] = {
        "temp_mean_c": 20.0,
        "temp_std_c": 4.0,
        "total_precipitation_mm": 50.0,
        "precip_std_mm": 3.0,
        "drought_index": 0.2
    }
    raw_bundle["nasa"] = {
        "root_zone_wetness": 0.5,
    }
    raw_bundle["gbif"] = {
        "species_count": 15
    }
    
    scores = compute_all_scores(raw_bundle)
    
    # Check keys
    assert "activity_score" in scores
    assert "activity_label" in scores
    assert "factor_scores" in scores
    
    # Check label mapping
    score_val = scores["activity_score"]
    valid_labels = [label for _, _, label in ACTIVITY_SCORE_LABELS]
    assert scores["activity_label"] in valid_labels

# ──────────────────────────────────────────────────────────────────────────────
# Test Anomaly Detector
# ──────────────────────────────────────────────────────────────────────────────
def test_detect_anomalies():
    # Construct a bundle guaranteed to trigger a CRITICAL anomaly (e.g., drought)
    lat, lon = 52.2053, 0.1218
    raw_bundle = get_full_mock_bundle(lat, lon)
    raw_bundle["climate"] = {
        "drought_index": 1.0, # CRITICAL
        "temp_std_c": 2.0,
        "total_precipitation_mm": 100.0
    }
    raw_bundle["nasa"] = {"root_zone_wetness": 0.5}
    raw_bundle["gbif"] = {"species_count": 20}
    
    anomalies = detect_anomalies(raw_bundle)
    assert len(anomalies) > 0, "Expected at least one anomaly"
    
    # Check if the critical drought anomaly is present
    critical_drought = next((a for a in anomalies if a["variable"] == "drought_index" and a["severity"] == "CRITICAL"), None)
    assert critical_drought is not None, "Expected CRITICAL drought anomaly"
    
    # Verify AI trigger logic
    assert has_ai_trigger_anomaly(anomalies) == True

def test_no_anomalies_for_perfect_conditions():
    # Construct a perfect bundle
    raw_bundle = {
        "climate": {
            "temp_std_c": 2.0,
            "total_precipitation_mm": 100.0,
            "drought_index": 0.1
        },
        "nasa": {
            "root_zone_wetness": 0.6
        },
        "gbif": {
            "species_count": 50
        },
        "soil": {
            "ph": 6.5,
            "organic_carbon_g_per_kg": 3.0,
            "nitrogen_g_per_kg": 2.0
        },
        "ndvi": {
            "ndvi": 0.8,
            "bare_soil_fraction": 0.1,
            "disturbance_score": 0.1
        },
        "pesticide": {
            "usage_ppm": 0.0,
            "applications_per_month": 0,
            "days_since_last_application": 100,
            "pesticide_type": "biopesticide"
        }
    }
    anomalies = detect_anomalies(raw_bundle)
    
    # Filter out INFO anomalies if there are any (our current logic only returns WARNING/CRITICAL usually)
    serious_anomalies = [a for a in anomalies if a["severity"] in ("WARNING", "CRITICAL")]
    assert len(serious_anomalies) == 0, f"Expected no serious anomalies, got {serious_anomalies}"
    assert has_ai_trigger_anomaly(anomalies) == False
