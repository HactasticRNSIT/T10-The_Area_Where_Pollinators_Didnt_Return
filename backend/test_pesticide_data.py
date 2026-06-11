from pesticide_data import (
    compute_pesticide_proxy,
    get_latest_country_pesticide_use,
    validate_pesticide_mappings,
)
from data_fetcher import _source_quality


import datetime
import math

def test_latest_country_pesticide_use_reads_bundled_dataset():
    india = get_latest_country_pesticide_use("IND")
    assert india is not None
    year = india["year"]
    current_year = datetime.datetime.now().year
    
    assert isinstance(year, int)
    assert 2018 <= year <= current_year
    assert india["tonnes"] > 0

    for country_code in ["USA", "BRA", "CHN"]:
        data = get_latest_country_pesticide_use(country_code)
        assert data is not None, f"Missing data for {country_code}"
        assert data["tonnes"] > 0, f"Zero or negative tonnes for {country_code}"
        assert data["country_code"] == country_code

    assert get_latest_country_pesticide_use("ZZZ") is None


def test_fixed_indian_state_codes_resolve_state_adjustments():
    expected = {
        "IN_CT": 1850.0,
        "IN_OR": 1405.0,
        "IN_UT": 217.2,
    }
    ind_data = get_latest_country_pesticide_use("IND")
    for zone_id, state_demand in expected.items():
        pesticide = compute_pesticide_proxy(zone_id)
        assert pesticide["source"] == "owid_fao_country_baseline_state_adjusted_and_crop_model"
        assert pesticide["country_pesticide_code"] == "IND"
        assert pesticide["country_pesticide_year"] == ind_data["year"]
        assert math.isclose(pesticide["country_pesticide_tonnes"], ind_data["tonnes"])
        assert math.isclose(pesticide["state_demand_mt_reference"], state_demand)
        assert "state_bio_demand_mt_reference" in pesticide
        assert "state_bio_consumption_mt_reference" in pesticide


def test_zone_baselines_preserve_scoring_interface():
    india_state = compute_pesticide_proxy("IN_KA_01")
    assert india_state["country_pesticide_code"] == "IND"
    assert india_state["state_code_reference"] == "IN_KA"
    assert math.isclose(india_state["state_demand_mt_reference"], 2100.0)

    usa_farm = compute_pesticide_proxy("FARM_G")
    assert usa_farm["source"] == "owid_fao_country_baseline_and_crop_model"
    assert usa_farm["country_pesticide_code"] == "USA"
    assert usa_farm["country_pesticide_tonnes"] > 0

    for field in (
        "usage_ppm",
        "applications_per_month",
        "days_since_last_application",
        "pesticide_type",
        "toxicity_multiplier",
    ):
        assert field in usa_farm


def test_mapping_validation_reports_country_misses_without_state_code_noise():
    warnings = validate_pesticide_mappings({"IN_CT", "IN_OR", "IN_UT", "IN_KA"})
    assert not any("IN_CT" in warning or "IN_OR" in warning or "IN_UT" in warning for warning in warnings)


def test_pesticide_dataset_sources_are_modelled_not_live():
    pesticide = compute_pesticide_proxy("IN_KA_01")
    assert _source_quality(pesticide["source"], pesticide.get("_fetch_error")) == "modelled"
