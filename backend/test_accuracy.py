
import sys
import os
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from main import analyse_zone
from config import ZONE_CROP_REGISTRY, get_anomaly_thresholds_for_zone

def test_state_accuracy(state_code, lat, lon):
    print(f"--- Testing {state_code} ({lat}, {lon}) ---")
    zone_id = f"{state_code}_TEST_01"
    
    # Run analysis
    result = analyse_zone(zone_id, lat, lon)
    
    # 1. Check Crop Registry Mapping
    expected_crops = set(ZONE_CROP_REGISTRY.get(state_code, {}).keys())
    actual_crops = set(result["crop_dependency"].keys())
    
    if expected_crops == actual_crops:
        print(f"[PASS] Crop mapping correct: {actual_crops}")
    else:
        print(f"[FAIL] Crop mapping mismatch! Expected {expected_crops}, got {actual_crops}")

    # 2. Check Factor Weights (from zone_weights.yaml)
    # Note: We can't easily check internal state of get_factor_weights_for_zone here, 
    # but we can check the weights returned in _meta.
    actual_weights = result["_meta"]["factor_weights"]
    # For IN_KA, pesticide_exposure should be 0.38
    if state_code == "IN_KA" and actual_weights["pesticide_exposure"] == 0.38:
        print(f"[PASS] Zone weight override (IN_KA) working: pesticide_exposure=0.38")
    elif state_code == "IN_RJ" and actual_weights["climate_variability"] == 0.22:
        print(f"[PASS] Zone weight override (IN_RJ) working: climate_variability=0.22")
    elif state_code not in ["IN_KA", "IN_RJ", "IN_HP", "IN_KL"]:
        # Should be default weights
        if actual_weights["pesticide_exposure"] == 0.32:
             print(f"[PASS] Default weights applied for {state_code}")

    # 3. Check Anomaly Thresholds (Logic test)
    # We can check if the thresholds used in detect_anomalies are correct by calling get_anomaly_thresholds_for_zone
    thresholds = get_anomaly_thresholds_for_zone(zone_id)
    if state_code == "IN_RJ":
        if thresholds["temp_variance_warning"] == 14.0:
            print(f"[PASS] Anomaly threshold override (IN_RJ) working: temp_variance_warning=14.0")
        else:
            print(f"[FAIL] Anomaly threshold override (IN_RJ) FAILED! Got {thresholds['temp_variance_warning']}")
    elif state_code == "IN_KL":
        if thresholds["ndvi_low_warning"] == 0.45:
            print(f"[PASS] Anomaly threshold override (IN_KL) working: ndvi_low_warning=0.45")
        else:
            print(f"[FAIL] Anomaly threshold override (IN_KL) FAILED! Got {thresholds['ndvi_low_warning']}")

    # 4. Check Pesticide Source
    pesticide_source = result["_meta"]["data_sources"]["pesticide"]
    if pesticide_source == "state_statistics_and_crop_model":
        print(f"[PASS] Pesticide source is correct: {pesticide_source}")
    else:
        print(f"[FAIL] Pesticide source mismatch! Got {pesticide_source}")

    # 5. Check Score Sanity
    score = result["activity_score"]
    label = result["activity_label"]
    print(f"Score: {score} ({label})")
    
    return result

if __name__ == "__main__":
    test_states = [
        ("IN_KA", 12.9716, 77.5946),
        ("IN_RJ", 26.9124, 75.7873),
        ("IN_KL", 10.8505, 76.2711),
        ("IN_UP", 26.8467, 80.9462),
    ]
    
    results = []
    for state, lat, lon in test_states:
        try:
            results.append(test_state_accuracy(state, lat, lon))
            print("\n")
        except Exception as e:
            print(f"[ERROR] Error testing {state}: {e}\n")
    
    # Save a sample output for verification
    with open("test_results_accuracy.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Full results saved to test_results_accuracy.json")
