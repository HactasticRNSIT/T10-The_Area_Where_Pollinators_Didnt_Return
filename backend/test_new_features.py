"""
test_new_features.py
====================
Unit tests for the new backend features implemented in this session:

  1. _fetch_open_meteo_agro  — new agro forecast endpoint
  2. fetch_open_meteo        — enriched output (humidity, VPD, soil temps)
                          and source label open_meteo_archive_plus_forecast_agro
  3. fetch_nasa_power        — Open-Meteo agro soil-moisture fallback when NASA fails
  4. _parse_soilgrids_layers — sand_g_per_kg, texture_class, soilgrids_depth,
                           soilgrids_property_count, _data_warning
  5. _build_output (main.py) — modelled / mock / live data_quality labelling

All external HTTP calls are mocked so no live network traffic is generated.
"""

import sys
import os
import json
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

# Allow imports from the backend directory
sys.path.insert(0, os.path.dirname(__file__))


# ──────────────────────────────────────────────────────────────────────────────
# Helper: build a minimal fake requests.Response
# ──────────────────────────────────────────────────────────────────────────────

def _make_response(data: dict, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = data
    r.raise_for_status = MagicMock()  # no-op for 200
    return r


def _make_error_response(status_code: int = 500) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return r


# ──────────────────────────────────────────────────────────────────────────────
# Fake Open-Meteo agro hourly payload
# ──────────────────────────────────────────────────────────────────────────────

_FAKE_AGRO_HOURLY = {
    "hourly": {
    "time":                    ["2026-05-16T00:00", "2026-05-16T01:00"],
    "relative_humidity_2m":    [72.0, 74.0],
    "vapour_pressure_deficit": [0.85, 0.90],
    "soil_temperature_0cm":    [28.5, 29.0],
    "soil_temperature_6cm":    [27.0, 27.5],
    "soil_moisture_0_to_1cm":  [0.25, 0.27],
    "soil_moisture_1_to_3cm":  [0.30, 0.31],
    "soil_moisture_3_to_9cm":  [0.33, 0.34],
    "soil_moisture_9_to_27cm": [0.35, 0.36],
    "soil_moisture_27_to_81cm":[0.38, 0.39],
    }
}

_FAKE_ARCHIVE_DAILY = {
    "daily": {
    "temperature_2m_max":         [32.0, 33.0, 31.5],
    "temperature_2m_min":         [22.0, 23.0, 21.5],
    "precipitation_sum":          [5.0, 0.0, 10.0],
    "wind_speed_10m_max":         [15.0, 12.0, 18.0],
    "et0_fao_evapotranspiration": [4.5,  4.2,  5.1],
    }
}


# ──────────────────────────────────────────────────────────────────────────────
# 1. _fetch_open_meteo_agro
# ──────────────────────────────────────────────────────────────────────────────
@patch("data_fetcher._get")
def test_successful_parse(mock_get):
    """Agro endpoint returns all expected keys when the API succeeds."""
    # Clear any lingering TTL cache entries
    import data_fetcher
    data_fetcher._cache.clear()

    mock_get.return_value = _make_response(_FAKE_AGRO_HOURLY)
    result = data_fetcher._fetch_open_meteo_agro(12.97, 77.59)

    assert result["source"] == "open_meteo_forecast_agro"
    assert result["_fetch_error"] is None
    assert round(result["relative_humidity_pct"], 1) == round(73.0, 1)
    assert round(result["vapour_pressure_deficit_kpa"], 2) == round(0.875, 2)
    assert round(result["soil_temp_surface_c"], 1) == round(28.75, 1)
    assert round(result["soil_temp_6cm_c"], 1) == round(27.25, 1)
    assert result["surface_soil_moisture"] is not None
    assert result["root_zone_wetness"] is not None
    assert result["hours_fetched"] == 2
@patch("data_fetcher._get", side_effect=Exception("connection refused"))
def test_network_failure_returns_error_dict(_):
    """Agro endpoint failure returns a dict with _fetch_error set (no exception raised)."""
    import data_fetcher
    data_fetcher._cache.clear()

    result = data_fetcher._fetch_open_meteo_agro(12.97, 77.59)
    assert "_fetch_error" in result
    assert "connection refused" in result["_fetch_error"]
    assert "unavailable" in result["source"]


# ──────────────────────────────────────────────────────────────────────────────
# 2. fetch_open_meteo — enriched output & source label
# ──────────────────────────────────────────────────────────────────────────────
@patch("data_fetcher._get")
def test_source_label_with_agro(mock_get):
    """Source label is open_meteo_archive_plus_forecast_agro when agro succeeds."""
    import data_fetcher
    data_fetcher._cache.clear()

    # First call → archive endpoint, second → agro forecast
    mock_get.side_effect = [
        _make_response(_FAKE_ARCHIVE_DAILY),
        _make_response(_FAKE_AGRO_HOURLY),
    ]
    result = data_fetcher.fetch_open_meteo(12.97, 77.59)

    assert result["source"] == "open_meteo_archive_plus_forecast_agro"
    assert "relative_humidity_pct" in result
    assert "vapour_pressure_deficit_kpa" in result
    assert "surface_soil_moisture" in result
    assert "root_zone_wetness_open_meteo" in result
    assert "soil_temp_surface_c" in result
    assert "soil_temp_6cm_c" in result
    assert "agro_source" in result
    assert result.get("_fetch_error") is None
@patch("data_fetcher._get")
def test_source_label_without_agro(mock_get):
    """Source label falls back to open_meteo when agro fails."""
    import data_fetcher
    data_fetcher._cache.clear()

    # Archive succeeds; agro raises
    mock_get.side_effect = [
        _make_response(_FAKE_ARCHIVE_DAILY),
        Exception("agro down"),
    ]
    result = data_fetcher.fetch_open_meteo(12.97, 77.59)

    assert result["source"] == "open_meteo"
    assert "_data_warning" in result
    assert "relative_humidity_pct" not in result
@patch("data_fetcher._get")
def test_climate_stats_correct(mock_get):
    """Core climate statistics are computed correctly from mock daily data."""
    import data_fetcher
    data_fetcher._cache.clear()

    mock_get.side_effect = [
        _make_response(_FAKE_ARCHIVE_DAILY),
        _make_response(_FAKE_AGRO_HOURLY),
    ]
    result = data_fetcher.fetch_open_meteo(12.97, 77.59)

    # mean([(32+22)/2, (33+23)/2, (31.5+21.5)/2]) = mean([27, 28, 26.5]) = 27.167
    assert round(result["temp_mean_c"], 1) == round(27.17, 1)
    assert result["total_precipitation_mm"] == 15.0
    assert result["days_fetched"] == 3


# ──────────────────────────────────────────────────────────────────────────────
# 3. fetch_nasa_power — Open-Meteo agro soil-moisture fallback
# ──────────────────────────────────────────────────────────────────────────────
@patch("data_fetcher._get")
def test_agro_fallback_when_nasa_fails(mock_get):
    """When NASA POWER fails, the function falls back to Open-Meteo agro soil moisture."""
    import data_fetcher
    data_fetcher._cache.clear()

    # NASA POWER call raises, then agro succeeds
    mock_get.side_effect = [
        Exception("NASA down"),
        _make_response(_FAKE_AGRO_HOURLY),
    ]
    result = data_fetcher.fetch_nasa_power(12.97, 77.59)

    assert "open_meteo_forecast_agro_modelled_nasa_fallback" in result["source"]
    assert result["root_zone_wetness"] is not None
    assert "_data_warning" in result
    assert "NASA POWER unavailable" in result["_data_warning"]
    assert "_fetch_error" in result  # original NASA error preserved
@patch("data_fetcher._get")
def test_mock_fallback_when_both_fail(mock_get):
    """When both NASA and Open-Meteo agro fail, returns mock_nasa_power."""
    import data_fetcher
    data_fetcher._cache.clear()

    mock_get.side_effect = Exception("all down")
    result = data_fetcher.fetch_nasa_power(12.97, 77.59)

    assert result["source"] == "nasa_unavailable"
    assert "_fetch_error" in result
@patch("data_fetcher._get")
def test_nasa_live_path(mock_get):
    """When NASA POWER is reachable, it returns source=nasa_power."""
    import data_fetcher
    data_fetcher._cache.clear()

    nasa_payload = {
        "properties": {
            "parameter": {
                "GWETROOT":    {"20260501": 0.42, "20260502": 0.44},
                "GWETPROF":    {"20260501": 0.38, "20260502": 0.40},
                "T2M":         {"20260501": 28.5, "20260502": 29.0},
                "PRECTOTCORR": {"20260501": 2.1,  "20260502": 0.5},
            }
        }
    }
    mock_get.return_value = _make_response(nasa_payload)
    result = data_fetcher.fetch_nasa_power(12.97, 77.59)

    assert result["source"] == "nasa_power"
    assert round(result["root_zone_wetness"], 2) == round(0.43, 2)
    assert result["_fetch_error"] is None


# ──────────────────────────────────────────────────────────────────────────────
# 4. _parse_soilgrids_layers — improved parsing
# ──────────────────────────────────────────────────────────────────────────────


def _make_layers(include_sand=True, include_nitrogen=True):
    """Build a minimal SoilGrids layers list."""
    def _layer(name, value):
        return {
            "name": name,
            "depths": [{"label": "0-30cm", "values": {"mean": value}}]
        }
    layers = [
        _layer("phh2o",   65),    # → 6.5
        _layer("soc",     18),    # → 1.8
        _layer("bdod",   135),    # → 1.35
        _layer("clay",   200),    # → 200 g/kg (20%)
    ]
    if include_sand:
        layers.append(_layer("sand", 650))   # → 650 g/kg (65%) → sandy_loam
    if include_nitrogen:
        layers.append(_layer("nitrogen", 120))  # → 1.2
    return layers

def test_full_parse():
    """All properties present → correct unit conversions and new fields."""
    from data_fetcher import _parse_soilgrids_layers, _SOILGRIDS_DEPTHS
    result = _parse_soilgrids_layers(_make_layers())

    assert result["source"] == "isric_soilgrids"
    assert round(result["ph"], 1) == round(6.5, 1)
    assert round(result["organic_carbon_g_per_kg"], 1) == round(1.8, 1)
    assert round(result["nitrogen_g_per_kg"], 1) == round(1.2, 1)
    assert round(result["bulk_density_g_per_cm3"], 2) == round(1.35, 2)
    assert round(result["clay_g_per_kg"], 0) == round(200.0, 0)

    # NEW: sand
    assert result["sand_g_per_kg"] is not None
    assert round(result["sand_g_per_kg"], 0) == round(650.0, 0)

    # NEW: texture_class (clay=20%, sand=65% → sandy_loam)
    assert result["texture_class"] == "sandy_loam"

    # NEW: soilgrids_depth matches config
    assert result["soilgrids_depth"] == ",".join(_SOILGRIDS_DEPTHS)

    # NEW: soilgrids_property_count
    assert result["soilgrids_property_count"] == 6

    # No warning when all present
    assert "_data_warning" not in result

def test_missing_property_triggers_warning():
    """Missing nitrogen + sand → _data_warning lists both."""
    from data_fetcher import _parse_soilgrids_layers
    result = _parse_soilgrids_layers(_make_layers(include_sand=False, include_nitrogen=False))

    assert "_data_warning" in result
    assert "nitrogen" in result["_data_warning"]
    assert "sand" in result["_data_warning"]

def test_texture_class_none_when_sand_missing():
    """texture_class is None when sand is absent."""
    from data_fetcher import _parse_soilgrids_layers
    result = _parse_soilgrids_layers(_make_layers(include_sand=False))
    assert result["texture_class"] is None

def test_texture_class_clay():
    """clay > 40% → texture_class == 'clay'."""
    from data_fetcher import _parse_soilgrids_layers

    def _layer(name, value):
        return {"name": name, "depths": [{"label": "0-30cm", "values": {"mean": value}}]}

    layers = [
        _layer("phh2o", 65), _layer("soc", 18), _layer("bdod", 135),
        _layer("clay", 450),   # 45% clay
        _layer("sand", 200),   # 20% sand
        _layer("nitrogen", 120),
    ]
    result = _parse_soilgrids_layers(layers)
    assert result["texture_class"] == "clay"


# ──────────────────────────────────────────────────────────────────────────────
# 5. _build_output (main.py) — data_quality labelling
# ──────────────────────────────────────────────────────────────────────────────


def _raw_with_sources(**source_map) -> dict:
    """Build a minimal raw dict with given source strings."""
    raw = {
        "_meta": {"lat": 12.97, "lon": 77.59, "zone_id": "IN_KA"},
        "_realtime": {},
    }
    defaults = {
        "climate": "open_meteo",
        "nasa": "nasa_power",
        "gbif": "gbif",
        "soil": "isric_soilgrids",
        "ndvi": "agromonitoring_satellite",
        "pesticide": "owid_fao_state",
        "visitation": "inaturalist",
    }
    defaults.update(source_map)
    for key, src in defaults.items():
        raw[key] = {"source": src}
    return raw

def _call_build_output(raw):
    from main import _build_output
    dummy_scores = {
        "activity_score": 75.0,
        "activity_label": "Moderate",
        "contribution_scores": {},
        "habitat_suitability_score": 60.0,
        "pollination_stress_index": "Medium",
        "crop_risk": {},
        "crop_dependency": {},
        "factor_scores": {},
        "factor_weights": {},
        "overall_stress": 0.35,
        "crop_dependency_basis": "zone_registry",
    }
    dummy_ai = {
        "biodiversity_insight": "test",
        "top_intervention": "test",
        "insight_source": "test",
    }
    dummy_brief = {}
    return _build_output(
        "IN_KA", 12.97, 77.59,
        dummy_scores, [], dummy_ai, raw, dummy_brief
    )

def test_live_sources_labelled_live():
    raw = _raw_with_sources()
    out = _call_build_output(raw)
    dq = out["_meta"]["data_quality"]
    assert dq["climate"] == "live"
    assert dq["nasa"] == "live"
    assert dq["gbif"] == "live"
    assert dq["soil"] == "live"
    assert dq["ndvi"] == "live"

def test_owid_fao_source_labelled_modelled():
    raw = _raw_with_sources(pesticide="owid_fao_state")
    out = _call_build_output(raw)
    dq = out["_meta"]["data_quality"]
    assert dq["pesticide"] == "modelled"

def test_modelled_keyword_in_source_labelled_modelled():
    """open_meteo_forecast_agro_modelled_nasa_fallback → modelled."""
    raw = _raw_with_sources(nasa="open_meteo_forecast_agro_modelled_nasa_fallback")
    out = _call_build_output(raw)
    dq = out["_meta"]["data_quality"]
    assert dq["nasa"] == "modelled"

def test_mock_source_labelled_fallback():
    raw = _raw_with_sources(soil="mock_soilgrids", gbif="mock_gbif")
    out = _call_build_output(raw)
    dq = out["_meta"]["data_quality"]
    assert dq["soil"] == "fallback"
    assert dq["gbif"] == "fallback"

def test_modelled_visitation_labelled_modelled():
    raw = _raw_with_sources(visitation="modelled_visitation")
    out = _call_build_output(raw)
    dq = out["_meta"]["data_quality"]
    assert dq["visitation"] == "modelled"

def test_unavailable_source_labelled_fallback():
    raw = _raw_with_sources(ndvi="agromonitoring_unavailable")
    out = _call_build_output(raw)
    dq = out["_meta"]["data_quality"]
    assert dq["ndvi"] == "fallback"

def test_modelled_visitation_caveat_is_prominent():
    raw = _raw_with_sources(visitation="modelled_visitation")
    out = _call_build_output(raw)
    caveats = out["_meta"]["data_caveats"]
    assert any("visitation" in item.lower() for item in caveats)


# ──────────────────────────────────────────────────────────────────────────────
# 6. Config sanity: new OPEN_METEO_AGRO_HOURLY_VARS present
# ──────────────────────────────────────────────────────────────────────────────


def test_agro_vars_defined():
    from config import OPEN_METEO_AGRO_HOURLY_VARS
    required = {
        "relative_humidity_2m",
        "vapour_pressure_deficit",
        "soil_temperature_0cm",
        "soil_temperature_6cm",
        "soil_moisture_0_to_1cm",
        "soil_moisture_1_to_3cm",
        "soil_moisture_3_to_9cm",
        "soil_moisture_9_to_27cm",
        "soil_moisture_27_to_81cm",
    }
    assert required.issubset(set(OPEN_METEO_AGRO_HOURLY_VARS))

def test_forecast_endpoint_defined():
    from config import API_ENDPOINTS
    assert "open_meteo_forecast" in API_ENDPOINTS
    assert "forecast" in API_ENDPOINTS["open_meteo_forecast"]



