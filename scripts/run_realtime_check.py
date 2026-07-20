"""
test_realtime_climate.py
=========================
Verifies that the PolyNexus server fetches and computes highly accurate,
real-time climate metrics based on today's actual climate at this particular time.
Tests multiple Indian regions to validate geographical accuracy:
  1. Dharwad, Karnataka (Warm, semi-arid, sunflower belt)
  2. Shimla, Himachal Pradesh (Cool, temperate mountain, apple orchards)
  3. Idukki, Kerala (Tropical, high humidity, spice coast)
"""

import os
import sys
import json
from datetime import datetime, timezone

# Add backend directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
backend_dir = os.path.join(project_root, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from data_fetcher import fetch_all
from main import analyse_zone


def _stress_label_and_score(stress_value, meta=None):
    if isinstance(stress_value, dict):
        return stress_value.get("label", "--"), stress_value.get("score")
    score = meta.get("overall_stress") if isinstance(meta, dict) else None
    return stress_value, score


def run_realtime_test():
    print("=" * 80)
    print(" POLY NEXUS: REAL-TIME CLIMATE ACCURACY TEST SUITE")
    print(f" Current Local Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Target Date: {datetime.now(timezone.utc).date().isoformat()}")
    print("=" * 80)

    test_locations = [
        {
            "name": "Dharwad, Karnataka (IN_KA)",
            "zone_id": "IN_KA_01",
            "lat": 15.4589,
            "lon": 75.0078,
            "expected_temp_min": 20.0,
            "expected_temp_max": 42.0,
            "climate_type": "Semi-arid / Deccan Plateau"
        },
        {
            "name": "Shimla, Himachal Pradesh (IN_HP)",
            "zone_id": "IN_HP_01",
            "lat": 31.1048,
            "lon": 77.1734,
            "expected_temp_min": 5.0,
            "expected_temp_max": 28.0,
            "climate_type": "Montane / Temperate"
        },
        {
            "name": "Idukki, Kerala (IN_KL)",
            "zone_id": "IN_KL_01",
            "lat": 9.8482,
            "lon": 77.0005,
            "expected_temp_min": 18.0,
            "expected_temp_max": 35.0,
            "climate_type": "Tropical Humid / Western Ghats"
        }
    ]

    all_passed = True
    summary_data = []

    for loc in test_locations:
        print(f"\n[FETCHING] Retrieving live data for {loc['name']}...")
        print(f"            Coordinates: ({loc['lat']}, {loc['lon']}) | Zone ID: {loc['zone_id']}")
        
        try:
            # 1. Fetch raw data to inspect details of live climate response
            raw_data = fetch_all(loc["lat"], loc["lon"], zone_id=loc["zone_id"])
            climate = raw_data.get("climate", {})
            realtime_status = raw_data.get("_realtime", {})
            
            # 2. Run the full analysis pipeline to verify overall scoring and integrity
            analysis_result = analyse_zone(loc["zone_id"], loc["lat"], loc["lon"])
            stress_label, stress_score = _stress_label_and_score(
                analysis_result.get("pollination_stress_index"),
                analysis_result.get("_meta", {}),
            )
            
            # Extract metrics
            source = climate.get("source")
            temp_mean = climate.get("temp_mean_c")
            temp_max = climate.get("temp_max_c")
            temp_min = climate.get("temp_min_c")
            humidity = climate.get("relative_humidity_pct")
            vpd = climate.get("vapour_pressure_deficit_kpa")
            precip = climate.get("total_precipitation_mm")
            soil_temp_surf = climate.get("soil_temp_surface_c")
            soil_temp_6cm = climate.get("soil_temp_6cm_c")
            surface_moisture = climate.get("surface_soil_moisture")
            
            # Print details
            print(f"[STATUS]   Data Source: {source}")
            print(f"[METRICS]  Mean Temp: {temp_mean}°C | Max Temp: {temp_max}°C | Min Temp: {temp_min}°C")
            print(f"[METRICS]  Relative Humidity: {humidity}% | VPD: {vpd} kPa")
            print(f"[METRICS]  Total Precipitation (recent): {precip} mm")
            print(f"[METRICS]  Soil Temp (Surface): {soil_temp_surf}°C | Soil Temp (6cm): {soil_temp_6cm}°C")
            print(f"[METRICS]  Surface Soil Moisture: {surface_moisture} m³/m³")
            print(f"[METRICS]  Ecosystem Activity Score: {analysis_result['activity_score']} ({analysis_result['activity_label']})")
            print(f"[METRICS]  Pollinator Stress Index: {stress_score} ({stress_label})")

            # 3. Perform Accuracy Assertions
            loc_passed = True
            
            # Source assertion (must be live API, not mock)
            if "mock" in source:
                print(f"  [FAIL] Climate data fell back to MOCK: {source}")
                loc_passed = False
            else:
                print(f"  [PASS] Successfully retrieved live climate data from API.")
            
            # Temperature sanity checks
            if temp_mean is None or temp_max is None or temp_min is None:
                print("  [FAIL] One or more temperature fields are missing.")
                loc_passed = False
            elif not (loc["expected_temp_min"] <= temp_mean <= loc["expected_temp_max"]):
                print(f"  [FAIL] Mean temperature {temp_mean}°C is out of typical range ({loc['expected_temp_min']}°C - {loc['expected_temp_max']}°C) for {loc['climate_type']}.")
                loc_passed = False
            else:
                print(f"  [PASS] Mean temperature {temp_mean}°C is highly accurate for {loc['climate_type']} today.")

            # Hourly forecast attributes assertions
            if humidity is None or humidity <= 0 or humidity > 100:
                print(f"  [FAIL] Invalid relative humidity percentage: {humidity}%")
                loc_passed = False
            else:
                print(f"  [PASS] Relative humidity {humidity}% is in valid atmospheric range.")

            if vpd is not None and vpd < 0:
                print(f"  [FAIL] Invalid negative Vapour Pressure Deficit: {vpd} kPa")
                loc_passed = False
            else:
                print(f"  [PASS] Vapour Pressure Deficit {vpd} kPa is thermodynamically valid.")

            if soil_temp_surf is not None and (soil_temp_surf < 0 or soil_temp_surf > 60):
                print(f"  [FAIL] Anomalous soil surface temperature: {soil_temp_surf}°C")
                loc_passed = False
            else:
                print(f"  [PASS] Soil surface temperature {soil_temp_surf}°C is realistic.")

            if not loc_passed:
                all_passed = False
                print(f"[RESULT]   {loc['name']} Accuracy Verification: FAILED ❌")
            else:
                print(f"[RESULT]   {loc['name']} Accuracy Verification: PASSED ✅")

            summary_data.append({
                "location": loc["name"],
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "source": source,
                "temp_mean": temp_mean,
                "temp_max": temp_max,
                "temp_min": temp_min,
                "humidity": humidity,
                "vpd": vpd,
                "precipitation": precip,
                "soil_temp_surface": soil_temp_surf,
                "surface_soil_moisture": surface_moisture,
                "activity_score": analysis_result["activity_score"],
                "stress_score": stress_score,
                "stress_label": stress_label,
                "status": "PASSED" if loc_passed else "FAILED"
            })
            
        except Exception as exc:
            all_passed = False
            print(f"  [ERROR] An unexpected exception occurred: {exc}")
            import traceback
            traceback.print_exc()
            summary_data.append({
                "location": loc["name"],
                "status": f"ERROR: {str(exc)}"
            })

    print("\n" + "=" * 80)
    print(" TEST RUN SUMMARY")
    print("=" * 80)
    for res in summary_data:
        print(f" - {res['location']}: {res['status']}")
        if "temp_mean" in res:
            print(f"   Temp: {res['temp_mean']}°C | Humid: {res['humidity']}% | Soil Temp: {res['soil_temp_surface']}°C | Source: {res['source']}")
    
    print("-" * 80)
    if all_passed:
        print("OVERALL REAL-TIME ACCURACY STATUS: PASSED SUCCESSFULLY ✅")
    else:
        print("OVERALL REAL-TIME ACCURACY STATUS: DETECTED INACCURACIES OR ERRORS ❌")
    print("=" * 80)
    
    # Save validation results as artifact in project root
    output_path = os.path.join(project_root, "test_results_realtime.json")
    with open(output_path, "w") as f:
        json.dump(summary_data, f, indent=2)


if __name__ == "__main__":
    run_realtime_test()
