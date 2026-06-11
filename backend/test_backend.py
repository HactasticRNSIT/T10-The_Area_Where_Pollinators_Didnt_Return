import pytest
import math
from scorer import score_pesticide_exposure, compute_all_scores, _bell_curve_stress
from anomaly_detector import detect_anomalies, has_ai_trigger_anomaly
from config import ACTIVITY_SCORE_LABELS, get_species_norm_for_zone
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
    # Override climate and nasa with explicit values (mock already has these but be explicit)
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

    scores = compute_all_scores(raw_bundle, zone_id="IN_KA")

    # Check keys
    assert "activity_score" in scores
    assert "activity_label" in scores
    assert "factor_scores" in scores

    # Check label mapping
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
    # Fix 9.5: add a stress-triggering visitation bundle so _check_visitation is exercised
    raw_bundle["visitation"] = {
        "source": "inaturalist",
        "avg_visitations_per_hour": 1.5,
        "expected_visitations_per_hour": 8.5,
        "visitation_ratio": 0.18,   # below CRITICAL threshold
        "twelve_week_visits_per_hour": [5.0, 4.5, 3.8, 3.2, 2.5, 2.2, 1.9, 1.7, 1.6, 1.5, 1.5, 1.5],
        "decline_rate_12w": 0.70,   # above CRITICAL decline threshold
        "pollination_timing_disruption": 0.82,
        "flowering_success_rate": 0.15,
        "recovery_volatility": 0.42,
        "total_observations": 5,
        "taxon_breakdown": {"Apis": 5},
        "_fetch_error": None,
    }

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
        },
        # Fix 9.6: add ideal visitation so _check_visitation is exercised in
        # the perfect-bundle test and we confirm it raises no anomalies.
        "visitation": {
            "source": "inaturalist",
            "avg_visitations_per_hour": 9.5,
            "expected_visitations_per_hour": 8.5,
            "visitation_ratio": 1.12,
            "twelve_week_visits_per_hour": [9.5] * 12,
            "decline_rate_12w": 0.0,
            "pollination_timing_disruption": 0.0,
            "flowering_success_rate": 0.95,
            "recovery_volatility": 0.0,
            "total_observations": 60,
            "taxon_breakdown": {"Apis": 40, "Bombus": 20},
            "_fetch_error": None,
        },
    }
    anomalies = detect_anomalies(raw_bundle)

    # Filter out INFO anomalies if there are any (our current logic only returns WARNING/CRITICAL usually)
    serious_anomalies = [a for a in anomalies if a["severity"] in ("WARNING", "CRITICAL")]
    assert len(serious_anomalies) == 0, f"Expected no serious anomalies, got {serious_anomalies}"
    assert has_ai_trigger_anomaly(anomalies) == False

# ──────────────────────────────────────────────────────────────────────────────
# Test Scorer / Config Helpers
# ──────────────────────────────────────────────────────────────────────────────

def test_bell_curve_stress_symmetry():
    # peak at 6.5, tolerance 1.0. At 6.5 stress is 0
    stress_peak = _bell_curve_stress(6.5, 6.5, 1.0)
    assert math.isclose(stress_peak, 0.0), "Expected zero stress at peak"

    # symmetry check at distance of 1.0
    stress_low = _bell_curve_stress(5.5, 6.5, 1.0)
    stress_high = _bell_curve_stress(7.5, 6.5, 1.0)
    assert stress_low > 0.0, "Expected non-zero stress off-peak"
    assert stress_high > 0.0, "Expected non-zero stress off-peak"
    assert abs(stress_low - stress_high) < 1e-5, "Expected symmetrical stress"

    # monotonic check
    stress_lower = _bell_curve_stress(4.5, 6.5, 1.0)
    assert stress_lower > stress_low, "Expected stress to increase as we move further from peak"


def test_get_species_norm_for_zone_overrides():
    # Kerala override (IN_KL) should return 18.0 for floral and 22.0 for resilience
    assert math.isclose(get_species_norm_for_zone("IN_KL_01", "floral"), 18.0)
    assert math.isclose(get_species_norm_for_zone("IN_KL_01", "resilience"), 22.0)

    # Check another Indian zone
    assert math.isclose(get_species_norm_for_zone("IN_KA_01", "floral"), 12.0)
    assert math.isclose(get_species_norm_for_zone("IN_KA_01", "resilience"), 15.0)

# ──────────────────────────────────────────────────────────────────────────────
# Test API endpoints (Snapshot)
# ──────────────────────────────────────────────────────────────────────────────

def test_analyse_endpoint_snapshot(snapshot, monkeypatch):
    from fastapi.testclient import TestClient
    from api import app
    from unittest.mock import patch

    client = TestClient(app)
    monkeypatch.setenv("POLYNEXUS_API_KEY", "test-key")

    raw_bundle = get_full_mock_bundle(12.0, 77.0)
    raw_bundle["climate"] = {"temp_mean_c": 25.0, "total_precipitation_mm": 50.0, "drought_index": 0.2, "temp_std_c": 2.0, "precip_std_mm": 5.0}
    raw_bundle["nasa"] = {"root_zone_wetness": 0.5}
    raw_bundle["gbif"] = {"species_count": 20}

    with patch("main.fetch_all", return_value=raw_bundle), \
         patch("main.fetch_open_meteo", return_value=raw_bundle["climate"]), \
         patch("main.get_ai_insights", return_value={"summary": "deterministic summary"}):
         
        response = client.get("/analyse?zone_id=IN_KA&lat=12.0&lon=77.0", headers={"X-API-Key": "test-key"})
        
        assert response.status_code == 200, response.text
        data = response.json()
        
        # Normalize varying data for stable snapshot
        if "raw" in data and "realtime_status" in data["raw"]:
            data["raw"]["realtime_status"]["generated_at"] = "2026-01-01"
            
        assert data == snapshot
