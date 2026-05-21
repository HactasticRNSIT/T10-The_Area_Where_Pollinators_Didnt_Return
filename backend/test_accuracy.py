import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from unittest.mock import patch

from config import (
    FACTOR_WEIGHTS,
    get_anomaly_thresholds_for_zone,
    get_crop_dependency_for_zone,
    get_factor_weights_for_zone,
)
from geo_classifier import resolve_agro_zone


def test_dynamic_crop_dependency_uses_geo_profile():
    geo_profile = {
        "crops": {"mustard": 0.8, "bajra": 0.35},
        "factor_weights": FACTOR_WEIGHTS,
    }

    assert get_crop_dependency_for_zone("IN_RJ_TEST_01", geo_profile) == {
        "mustard": 0.8,
        "bajra": 0.35,
    }


def test_dynamic_classifier_arid_profile_without_legacy_registry():
    """
    When both the state registry and LLM lookup are unavailable, resolve_agro_zone
    must return the climate-zone fallback crops for a low-precipitation input.

    Patching both tiers prevents live network calls and tests the deterministic
    heuristic path that runs entirely from climate signals.
    """
    with (
        patch("geo_classifier._reverse_geocode_state", return_value=None),
        patch("geo_classifier._fetch_groq_crops", return_value=None),
    ):
        profile = resolve_agro_zone(
            27.2152,
            77.4941,
            {
                "elevation": 180,
                "temp_mean_c": 31.0,
                "total_precipitation_mm": 8.0,
                "days_fetched": 30,
            },
        )

    assert profile["classification"] == "Arid / Semi-Arid"
    assert {"mustard", "bajra", "cumin"}.issubset(profile["crops"])
    assert profile["crop_source"] == "climate_zone_fallback"


def test_state_registry_crop_lookup():
    """
    When Nominatim returns 'Kerala', resolve_agro_zone must serve crops
    from the static state registry without touching the LLM.
    """
    with (
        patch("geo_classifier._reverse_geocode_state", return_value="Kerala"),
        patch("geo_classifier._fetch_groq_crops") as mock_llm,
    ):
        profile = resolve_agro_zone(
            10.5,
            76.2,
            {"elevation": 50, "temp_mean_c": 27.0, "total_precipitation_mm": 200.0, "days_fetched": 30},
        )

    mock_llm.assert_not_called()
    assert profile["crop_source"] == "state_registry"
    assert "cardamom" in profile["crops"]
    assert "coconut" in profile["crops"]
    assert profile["crops"]["cardamom"] >= 0.80


def test_llm_fallback_when_state_not_in_registry():
    """
    When Nominatim returns a state not in the registry, the LLM tier fires.
    """
    fake_crops = {"teff": 0.30, "coffee": 0.70}
    with (
        patch("geo_classifier._reverse_geocode_state", return_value="Somaliland"),
        patch("geo_classifier._fetch_groq_crops", return_value=fake_crops),
    ):
        profile = resolve_agro_zone(
            9.0, 45.3,
            {"elevation": 400, "temp_mean_c": 28.0, "total_precipitation_mm": 60.0, "days_fetched": 30},
        )

    assert profile["crop_source"] == "groq_llm"
    assert "coffee" in profile["crops"]


def test_zone_weight_overrides_still_work():
    assert get_factor_weights_for_zone("IN_KA_TEST_01")["pesticide_exposure"] == 0.38
    assert get_factor_weights_for_zone("IN_RJ_TEST_01")["climate_variability"] == 0.22
    assert get_factor_weights_for_zone("IN_UNKNOWN_TEST") == FACTOR_WEIGHTS


def test_anomaly_threshold_overrides_still_work():
    rajasthan = get_anomaly_thresholds_for_zone("IN_RJ_TEST_01")
    kerala = get_anomaly_thresholds_for_zone("IN_KL_TEST_01")

    assert rajasthan["temp_variance_warning"] == 14.0
    assert kerala["ndvi_low_warning"] == 0.45
