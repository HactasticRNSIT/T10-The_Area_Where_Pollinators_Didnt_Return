def get_full_mock_bundle(lat: float, lon: float) -> dict:
    return {
        "climate": {
            "source": "open_meteo",
            "temp_mean_c": 20.0,
            "temp_std_c": 4.0,
            "total_precipitation_mm": 50.0,
            "precip_std_mm": 3.0,
            "drought_index": 0.2
        },
        "nasa": {
            "source": "nasa_power",
            "root_zone_wetness": 0.5,
        },
        "gbif": {
            "source": "gbif",
            "species_count": 15
        },
        "soil": {
            "source": "isric_soilgrids",
            "ph": 6.5,
            "organic_carbon_g_per_kg": 3.0,
            "nitrogen_g_per_kg": 2.0
        },
        "ndvi": {
            "source": "eosda_satellite",
            "ndvi": 0.8,
            "bare_soil_fraction": 0.1,
            "disturbance_score": 0.1
        },
        "pesticide": {
            "source": "owid_fao_country_baseline_and_crop_model",
            "usage_ppm": 0.0,
            "applications_per_month": 0,
            "days_since_last_application": 100,
            "pesticide_type": "biopesticide"
        },
        # Fix 4.1: provide a realistic visitation bundle so tests exercise the
        # pollination factor path in compute_all_scores and detect_anomalies.
        "visitation": {
            "source": "inaturalist",
            "avg_visitations_per_hour": 9.0,
            "expected_visitations_per_hour": 8.5,
            "visitation_ratio": 1.06,
            "twelve_week_visits_per_hour": [8.8, 9.1, 9.3, 9.0, 8.9, 9.2, 9.1, 8.7, 9.0, 9.3, 8.8, 9.0],
            "decline_rate_12w": 0.0,
            "pollination_timing_disruption": 0.0,
            "flowering_success_rate": 0.90,
            "recovery_volatility": 0.0,
            "total_observations": 42,
            "taxon_breakdown": {"Apis": 28, "Bombus": 14},
            "_fetch_error": None,
        },
        "_meta": {
            "lat": lat,
            "lon": lon,
            "zone_id": "test_zone",
            "geo_profile": {
                "classification": "Tropical Wet",
                "crops": {"rice": 0.5},
                "crop_source": "test",
                "factor_weights": {}
            }
        }
    }
