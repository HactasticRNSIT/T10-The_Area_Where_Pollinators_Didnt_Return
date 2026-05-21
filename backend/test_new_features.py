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
import unittest
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

class TestFetchOpenMeteoAgro(unittest.TestCase):

    @patch("data_fetcher._get")
    def test_successful_parse(self, mock_get):
        """Agro endpoint returns all expected keys when the API succeeds."""
        # Clear any lingering TTL cache entries
        import data_fetcher
        data_fetcher._cache.clear()

        mock_get.return_value = _make_response(_FAKE_AGRO_HOURLY)
        result = data_fetcher._fetch_open_meteo_agro(12.97, 77.59)

        self.assertEqual(result["source"], "open_meteo_forecast_agro")
        self.assertIsNone(result["_fetch_error"])
        self.assertAlmostEqual(result["relative_humidity_pct"], 73.0, places=1)
        self.assertAlmostEqual(result["vapour_pressure_deficit_kpa"], 0.875, places=2)
        self.assertAlmostEqual(result["soil_temp_surface_c"], 28.75, places=1)
        self.assertAlmostEqual(result["soil_temp_6cm_c"], 27.25, places=1)
        self.assertIsNotNone(result["surface_soil_moisture"])
        self.assertIsNotNone(result["root_zone_wetness"])
        self.assertEqual(result["hours_fetched"], 2)

    @patch("data_fetcher._get", side_effect=Exception("connection refused"))
    def test_network_failure_returns_error_dict(self, _):
        """Agro endpoint failure returns a dict with _fetch_error set (no exception raised)."""
        import data_fetcher
        data_fetcher._cache.clear()

        result = data_fetcher._fetch_open_meteo_agro(12.97, 77.59)
        self.assertIn("_fetch_error", result)
        self.assertIn("connection refused", result["_fetch_error"])
        self.assertIn("unavailable", result["source"])


# ──────────────────────────────────────────────────────────────────────────────
# 2. fetch_open_meteo — enriched output & source label
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchOpenMeteoEnriched(unittest.TestCase):

    @patch("data_fetcher._get")
    def test_source_label_with_agro(self, mock_get):
        """Source label is open_meteo_archive_plus_forecast_agro when agro succeeds."""
        import data_fetcher
        data_fetcher._cache.clear()

        # First call → archive endpoint, second → agro forecast
        mock_get.side_effect = [
            _make_response(_FAKE_ARCHIVE_DAILY),
            _make_response(_FAKE_AGRO_HOURLY),
        ]
        result = data_fetcher.fetch_open_meteo(12.97, 77.59)

        self.assertEqual(result["source"], "open_meteo_archive_plus_forecast_agro")
        self.assertIn("relative_humidity_pct", result)
        self.assertIn("vapour_pressure_deficit_kpa", result)
        self.assertIn("surface_soil_moisture", result)
        self.assertIn("root_zone_wetness_open_meteo", result)
        self.assertIn("soil_temp_surface_c", result)
        self.assertIn("soil_temp_6cm_c", result)
        self.assertIn("agro_source", result)
        self.assertIsNone(result.get("_fetch_error"))

    @patch("data_fetcher._get")
    def test_source_label_without_agro(self, mock_get):
        """Source label falls back to open_meteo when agro fails."""
        import data_fetcher
        data_fetcher._cache.clear()

        # Archive succeeds; agro raises
        mock_get.side_effect = [
            _make_response(_FAKE_ARCHIVE_DAILY),
            Exception("agro down"),
        ]
        result = data_fetcher.fetch_open_meteo(12.97, 77.59)

        self.assertEqual(result["source"], "open_meteo")
        self.assertIn("_data_warning", result)
        self.assertNotIn("relative_humidity_pct", result)

    @patch("data_fetcher._get")
    def test_climate_stats_correct(self, mock_get):
        """Core climate statistics are computed correctly from mock daily data."""
        import data_fetcher
        data_fetcher._cache.clear()

        mock_get.side_effect = [
            _make_response(_FAKE_ARCHIVE_DAILY),
            _make_response(_FAKE_AGRO_HOURLY),
        ]
        result = data_fetcher.fetch_open_meteo(12.97, 77.59)

        # mean([(32+22)/2, (33+23)/2, (31.5+21.5)/2]) = mean([27, 28, 26.5]) = 27.167
        self.assertAlmostEqual(result["temp_mean_c"], 27.17, places=1)
        self.assertEqual(result["total_precipitation_mm"], 15.0)
        self.assertEqual(result["days_fetched"], 3)


# ──────────────────────────────────────────────────────────────────────────────
# 3. fetch_nasa_power — Open-Meteo agro soil-moisture fallback
# ──────────────────────────────────────────────────────────────────────────────

class TestNASAPowerFallback(unittest.TestCase):

    @patch("data_fetcher._get")
    def test_agro_fallback_when_nasa_fails(self, mock_get):
        """When NASA POWER fails, the function falls back to Open-Meteo agro soil moisture."""
        import data_fetcher
        data_fetcher._cache.clear()

        # NASA POWER call raises, then agro succeeds
        mock_get.side_effect = [
            Exception("NASA down"),
            _make_response(_FAKE_AGRO_HOURLY),
        ]
        result = data_fetcher.fetch_nasa_power(12.97, 77.59)

        self.assertIn("open_meteo_forecast_agro_modelled_nasa_fallback", result["source"])
        self.assertIsNotNone(result["root_zone_wetness"])
        self.assertIn("_data_warning", result)
        self.assertIn("NASA POWER unavailable", result["_data_warning"])
        self.assertIn("_fetch_error", result)  # original NASA error preserved

    @patch("data_fetcher._get")
    def test_mock_fallback_when_both_fail(self, mock_get):
        """When both NASA and Open-Meteo agro fail, returns mock_nasa_power."""
        import data_fetcher
        data_fetcher._cache.clear()

        mock_get.side_effect = Exception("all down")
        result = data_fetcher.fetch_nasa_power(12.97, 77.59)

        self.assertEqual(result["source"], "mock_nasa_power")
        self.assertIn("_fetch_error", result)

    @patch("data_fetcher._get")
    def test_nasa_live_path(self, mock_get):
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

        self.assertEqual(result["source"], "nasa_power")
        self.assertAlmostEqual(result["root_zone_wetness"], 0.43, places=2)
        self.assertIsNone(result["_fetch_error"])


# ──────────────────────────────────────────────────────────────────────────────
# 4. _parse_soilgrids_layers — improved parsing
# ──────────────────────────────────────────────────────────────────────────────

class TestParseSoilGridsLayers(unittest.TestCase):

    def _make_layers(self, include_sand=True, include_nitrogen=True):
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

    def test_full_parse(self):
        """All properties present → correct unit conversions and new fields."""
        from data_fetcher import _parse_soilgrids_layers, _SOILGRIDS_DEPTHS
        result = _parse_soilgrids_layers(self._make_layers())

        self.assertEqual(result["source"], "isric_soilgrids")
        self.assertAlmostEqual(result["ph"], 6.5, places=1)
        self.assertAlmostEqual(result["organic_carbon_g_per_kg"], 1.8, places=1)
        self.assertAlmostEqual(result["nitrogen_g_per_kg"], 1.2, places=1)
        self.assertAlmostEqual(result["bulk_density_g_per_cm3"], 1.35, places=2)
        self.assertAlmostEqual(result["clay_g_per_kg"], 200.0, places=0)

        # NEW: sand
        self.assertIsNotNone(result["sand_g_per_kg"])
        self.assertAlmostEqual(result["sand_g_per_kg"], 650.0, places=0)

        # NEW: texture_class (clay=20%, sand=65% → sandy_loam)
        self.assertEqual(result["texture_class"], "sandy_loam")

        # NEW: soilgrids_depth matches config
        self.assertEqual(result["soilgrids_depth"], ",".join(_SOILGRIDS_DEPTHS))

        # NEW: soilgrids_property_count
        self.assertEqual(result["soilgrids_property_count"], 6)

        # No warning when all present
        self.assertNotIn("_data_warning", result)

    def test_missing_property_triggers_warning(self):
        """Missing nitrogen + sand → _data_warning lists both."""
        from data_fetcher import _parse_soilgrids_layers
        result = _parse_soilgrids_layers(self._make_layers(include_sand=False, include_nitrogen=False))

        self.assertIn("_data_warning", result)
        self.assertIn("nitrogen", result["_data_warning"])
        self.assertIn("sand", result["_data_warning"])

    def test_texture_class_none_when_sand_missing(self):
        """texture_class is None when sand is absent."""
        from data_fetcher import _parse_soilgrids_layers
        result = _parse_soilgrids_layers(self._make_layers(include_sand=False))
        self.assertIsNone(result["texture_class"])

    def test_texture_class_clay(self):
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
        self.assertEqual(result["texture_class"], "clay")


# ──────────────────────────────────────────────────────────────────────────────
# 5. _build_output (main.py) — data_quality labelling
# ──────────────────────────────────────────────────────────────────────────────

class TestDataQualityLabelling(unittest.TestCase):

    def _raw_with_sources(self, **source_map) -> dict:
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

    def _call_build_output(self, raw):
        from main import _build_output
        dummy_scores = {
            "activity_score": 75.0,
            "activity_label": "Moderate",
            "contribution_scores": {},
            "habitat_suitability_score": 0.6,
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

    def test_live_sources_labelled_live(self):
        raw = self._raw_with_sources()
        out = self._call_build_output(raw)
        dq = out["_meta"]["data_quality"]
        self.assertEqual(dq["climate"], "live")
        self.assertEqual(dq["nasa"], "live")
        self.assertEqual(dq["gbif"], "live")
        self.assertEqual(dq["soil"], "live")
        self.assertEqual(dq["ndvi"], "live")

    def test_owid_fao_source_labelled_modelled(self):
        raw = self._raw_with_sources(pesticide="owid_fao_state")
        out = self._call_build_output(raw)
        dq = out["_meta"]["data_quality"]
        self.assertEqual(dq["pesticide"], "modelled")

    def test_modelled_keyword_in_source_labelled_modelled(self):
        """open_meteo_forecast_agro_modelled_nasa_fallback → modelled."""
        raw = self._raw_with_sources(nasa="open_meteo_forecast_agro_modelled_nasa_fallback")
        out = self._call_build_output(raw)
        dq = out["_meta"]["data_quality"]
        self.assertEqual(dq["nasa"], "modelled")

    def test_mock_source_labelled_fallback(self):
        raw = self._raw_with_sources(soil="mock_soilgrids", gbif="mock_gbif")
        out = self._call_build_output(raw)
        dq = out["_meta"]["data_quality"]
        self.assertEqual(dq["soil"], "fallback")
        self.assertEqual(dq["gbif"], "fallback")

    def test_modelled_visitation_labelled_modelled(self):
        raw = self._raw_with_sources(visitation="modelled_visitation")
        out = self._call_build_output(raw)
        dq = out["_meta"]["data_quality"]
        self.assertEqual(dq["visitation"], "modelled")

    def test_unavailable_source_labelled_fallback(self):
        raw = self._raw_with_sources(ndvi="agromonitoring_unavailable")
        out = self._call_build_output(raw)
        dq = out["_meta"]["data_quality"]
        self.assertEqual(dq["ndvi"], "fallback")

    def test_modelled_visitation_caveat_is_prominent(self):
        raw = self._raw_with_sources(visitation="modelled_visitation")
        out = self._call_build_output(raw)
        caveats = out["_meta"]["data_caveats"]
        self.assertTrue(any("visitation" in item.lower() for item in caveats))


# ──────────────────────────────────────────────────────────────────────────────
# 6. Config sanity: new OPEN_METEO_AGRO_HOURLY_VARS present
# ──────────────────────────────────────────────────────────────────────────────

class TestConfigNewVars(unittest.TestCase):

    def test_agro_vars_defined(self):
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
        self.assertTrue(required.issubset(set(OPEN_METEO_AGRO_HOURLY_VARS)))

    def test_forecast_endpoint_defined(self):
        from config import API_ENDPOINTS
        self.assertIn("open_meteo_forecast", API_ENDPOINTS)
        self.assertIn("forecast", API_ENDPOINTS["open_meteo_forecast"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
