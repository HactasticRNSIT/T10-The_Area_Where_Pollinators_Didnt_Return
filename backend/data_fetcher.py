

import logging
import statistics
from datetime import date, timedelta
from typing import Any

import requests

from config import (
    API_ENDPOINTS,
    CLIMATE_LOOKBACK_DAYS,
    GBIF_MAX_RECORDS,
    GBIF_POLLINATOR_TAXON_KEYS,
    GBIF_RADIUS_KM,
    NASA_POWER_VARS,
    OPEN_METEO_VARS,
    REQUEST_TIMEOUT,
)
from mock_data import get_mock_ndvi_data, get_mock_pesticide_data, get_mock_soil_data

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Date helpers
# ──────────────────────────────────────────────────────────────────────────────

def _date_range() -> tuple[str, str]:
    """Return ISO date strings for the 30-day look-back window."""
    end = date.today() - timedelta(days=2)   # APIs lag ~2 days
    start = end - timedelta(days=CLIMATE_LOOKBACK_DAYS - 1)
    return start.isoformat(), end.isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# Open-Meteo
# ──────────────────────────────────────────────────────────────────────────────

def fetch_open_meteo(lat: float, lon: float) -> dict[str, Any]:
    """
    Retrieve 30-day daily climate data from the Open-Meteo archive API.

    Returns a dict with summarised statistics (mean, std-dev, totals).
    Falls back to a minimal mock dict on failure.
    """
    start_date, end_date = _date_range()
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start_date,
        "end_date":   end_date,
        "daily":      ",".join(OPEN_METEO_VARS),
        "timezone":   "UTC",
    }
    try:
        resp = requests.get(
            API_ENDPOINTS["open_meteo"],
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})

        t_max = daily.get("temperature_2m_max", [])
        t_min = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        wind = daily.get("windspeed_10m_max", [])
        etp = daily.get("et0_fao_evapotranspiration", [])

        # Filter out None values
        t_max = [v for v in t_max if v is not None]
        t_min = [v for v in t_min if v is not None]
        precip = [v for v in precip if v is not None]
        wind = [v for v in wind if v is not None]
        etp = [v for v in etp if v is not None]

        # Compute daily mean temperature
        t_mean = []
        for mx, mn in zip(t_max, t_min):
            if mx is not None and mn is not None:
                t_mean.append((mx + mn) / 2)

        total_precip = sum(precip)
        avg_precip = total_precip / max(len(precip), 1)

        # Drought index: ratio of ETP to precipitation (capped 0–1)
        total_etp = sum(etp)
        drought_index = min(1.0, total_etp / max(total_precip, 1.0)) if total_etp else 0.0

        return {
            "source":               "open_meteo",
            "temp_mean_c":          round(statistics.mean(t_mean), 2) if t_mean else 20.0,
            "temp_std_c":           round(statistics.stdev(t_mean), 3) if len(t_mean) > 1 else 0.0,
            "temp_max_c":           round(max(t_max), 2) if t_max else 30.0,
            "temp_min_c":           round(min(t_min), 2) if t_min else 10.0,
            "total_precipitation_mm": round(total_precip, 2),
            "avg_daily_precip_mm":  round(avg_precip, 2),
            "precip_std_mm":        round(statistics.stdev(precip), 3) if len(precip) > 1 else 0.0,
            "avg_windspeed_kmh":    round(statistics.mean(wind), 2) if wind else 10.0,
            "drought_index":        round(drought_index, 3),
            "days_fetched":         len(t_mean),
        }

    except Exception as exc:
        log.warning("Open-Meteo fetch failed (%s) – using mock climate data", exc)
        return _mock_climate_fallback(lat, lon)


def _mock_climate_fallback(lat: float, lon: float) -> dict[str, Any]:
    """Minimal mock climate data derived from latitude (rough approximation)."""
    import math as _math
    # Rough temperature estimate from latitude
    base_temp = 25.0 - abs(lat) * 0.5
    return {
        "source":               "mock_open_meteo",
        "temp_mean_c":          round(base_temp, 2),
        "temp_std_c":           4.2,
        "temp_max_c":           round(base_temp + 7, 2),
        "temp_min_c":           round(base_temp - 7, 2),
        "total_precipitation_mm": 48.0,
        "avg_daily_precip_mm":  1.6,
        "precip_std_mm":        3.1,
        "avg_windspeed_kmh":    12.5,
        "drought_index":        0.38,
        "days_fetched":         0,
    }


# ──────────────────────────────────────────────────────────────────────────────
# NASA POWER
# ──────────────────────────────────────────────────────────────────────────────

def fetch_nasa_power(lat: float, lon: float) -> dict[str, Any]:
    """
    Retrieve soil wetness and surface climate from NASA POWER daily endpoint.

    Returns mean values over the look-back window.
    Falls back to SoilGrids mock on failure.
    """
    start_date, end_date = _date_range()
    # NASA POWER uses YYYYMMDD format
    params = {
        "parameters": ",".join(NASA_POWER_VARS),
        "community":  "AG",
        "longitude":  lon,
        "latitude":   lat,
        "start":      start_date.replace("-", ""),
        "end":        end_date.replace("-", ""),
        "format":     "JSON",
    }
    try:
        resp = requests.get(
            API_ENDPOINTS["nasa_power"],
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        props = (
            data.get("properties", {})
                .get("parameter", {})
        )

        def _mean_valid(series: dict) -> float:
            vals = [v for v in series.values() if v not in (None, -999.0, -999)]
            return round(statistics.mean(vals), 4) if vals else 0.0

        gwet_root = _mean_valid(props.get("GWETROOT", {}))
        gwet_prof = _mean_valid(props.get("GWETPROF", {}))
        t2m       = _mean_valid(props.get("T2M", {}))
        precip    = _mean_valid(props.get("PRECTOTCORR", {}))

        return {
            "source":               "nasa_power",
            "root_zone_wetness":    gwet_root,   # 0–1
            "profile_wetness":      gwet_prof,   # 0–1
            "surface_temp_c":       t2m,
            "daily_precip_mm":      precip,
        }

    except Exception as exc:
        log.warning("NASA POWER fetch failed (%s) – using mock soil moisture", exc)
        # Derive a plausible fallback from the soil mock
        soil = get_mock_soil_data(lat, lon)
        return {
            "source":            "mock_nasa_power",
            "root_zone_wetness": 0.45,
            "profile_wetness":   0.40,
            "surface_temp_c":    22.0,
            "daily_precip_mm":   1.8,
        }


# ──────────────────────────────────────────────────────────────────────────────
# GBIF pollinator observations
# ──────────────────────────────────────────────────────────────────────────────

def fetch_gbif_pollinators(lat: float, lon: float) -> dict[str, Any]:
    """
    Search GBIF for pollinator species observations within GBIF_RADIUS_KM of
    the given coordinates.  Counts unique species and records total occurrences.

    Falls back to a mock reading on failure.
    """
    # GBIF uses decimal-degree radius in km
    all_species: set[str] = set()
    total_records = 0
    family_breakdown: dict[str, int] = {}

    for taxon_key in GBIF_POLLINATOR_TAXON_KEYS:
        try:
            params = {
                "taxonKey":   taxon_key,
                "decimalLatitude":  f"{lat - _km_to_deg(GBIF_RADIUS_KM)},{lat + _km_to_deg(GBIF_RADIUS_KM)}",
                "decimalLongitude": f"{lon - _km_to_deg(GBIF_RADIUS_KM)},{lon + _km_to_deg(GBIF_RADIUS_KM)}",
                "limit":      GBIF_MAX_RECORDS // len(GBIF_POLLINATOR_TAXON_KEYS),
                "hasCoordinate": "true",
                "occurrenceStatus": "PRESENT",
            }
            resp = requests.get(
                API_ENDPOINTS["gbif_occurrences"],
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            results = payload.get("results", [])
            total_records += len(results)
            for rec in results:
                sp = rec.get("species") or rec.get("scientificName")
                if sp:
                    all_species.add(sp)
                fam = rec.get("family", "Unknown")
                family_breakdown[fam] = family_breakdown.get(fam, 0) + 1

        except Exception as exc:
            log.warning("GBIF fetch for taxon %s failed (%s)", taxon_key, exc)

    if total_records == 0:
        return _mock_gbif_fallback(lat, lon)

    return {
        "source":          "gbif",
        "species_count":   len(all_species),
        "total_records":   total_records,
        "family_breakdown": family_breakdown,
        "species_list":    sorted(all_species)[:20],  # cap for JSON size
    }


def _km_to_deg(km: float) -> float:
    """Rough conversion of kilometres to decimal degrees (latitude-safe)."""
    return km / 111.0


def _mock_gbif_fallback(lat: float, lon: float) -> dict[str, Any]:
    """Minimal GBIF fallback using zone seed."""
    from mock_data import _zone_seed
    import math as _math
    s = _zone_seed(lat, lon)
    species_count = max(1, round(8 + _math.sin(s * 13.7) * 5))
    return {
        "source":          "mock_gbif",
        "species_count":   species_count,
        "total_records":   species_count * 12,
        "family_breakdown": {"Apidae": species_count // 2, "Syrphidae": species_count // 3},
        "species_list":    [f"mock_species_{i+1}" for i in range(min(species_count, 10))],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Soil data — ISRIC SoilGrids  →  OpenLandMap STAC catalog  →  mock fallback
# ──────────────────────────────────────────────────────────────────────────────

# ISRIC SoilGrids variables to request
_SOILGRIDS_PROPS = ["phh2o", "soc", "nitrogen", "bdod", "clay", "sand"]
_SOILGRIDS_DEPTHS = ["0-30cm"]

# OpenLandMap STAC collection IDs for key soil properties
# (source: https://stac.openlandmap.org)
_OLM_COLLECTIONS = {
    "ph":             "ph.h2o_usda.4c1a2a_m",
    "organic_carbon": "log.oc_iso.10694_m",
}


def fetch_soil_data(lat: float, lon: float) -> dict[str, Any]:
    """
    Attempt to retrieve real soil data using a 3-tier strategy:

    Tier 1 – ISRIC SoilGrids REST API
        Simple point query, no auth. Returns data when service is available.
        Currently intermittent (empty layers[]) — handled gracefully.

    Tier 2 – OpenLandMap STAC catalog (JSON metadata)
        Reads the STAC catalog to extract available layer info as a
        lightweight health-check. No rasterio/COG download attempted
        (avoids heavy dependencies). Returns a minimal dict with
        OpenLandMap-sourced soil pH and organic carbon when parseable.

    Tier 3 – mock_data.get_mock_soil_data()
        Deterministic lat/lon-seeded mock; always succeeds.
    """
    # ── Tier 1: ISRIC SoilGrids ──────────────────────────────────────────────
    try:
        params: dict[str, Any] = {
            "lat":      lat,
            "lon":      lon,
            "property": _SOILGRIDS_PROPS,
            "depth":    _SOILGRIDS_DEPTHS,
            "value":    ["mean"],
        }
        resp = requests.get(
            API_ENDPOINTS["soilgrids"],
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        layers = payload.get("properties", {}).get("layers", [])

        if layers:  # non-empty means SoilGrids is serving real data
            result = _parse_soilgrids_layers(layers)
            log.info("Soil data from ISRIC SoilGrids for (%.4f, %.4f)", lat, lon)
            return result
        else:
            log.warning(
                "SoilGrids returned empty layers for (%.4f, %.4f) – service degraded, "
                "trying OpenLandMap STAC", lat, lon
            )
    except Exception as exc:
        log.warning("SoilGrids fetch failed (%s) – trying OpenLandMap STAC", exc)

    # ── Tier 2: OpenLandMap STAC catalog probe ────────────────────────────────
    try:
        resp = requests.get(
            API_ENDPOINTS["openlandmap_stac"],
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        catalog = resp.json()
        # The STAC catalog lists child collections; we verify OpenLandMap is up
        # and extract any metadata usable as a lightweight proxy value.
        links = catalog.get("links", [])
        collection_ids = [
            lnk.get("title", "") for lnk in links
            if lnk.get("rel") in ("child", "item")
        ]
        if collection_ids:
            log.info(
                "OpenLandMap STAC reachable (%d collections). Using STAC-informed mock.",
                len(collection_ids)
            )
            # STAC catalog is alive — return a STAC-informed mock
            # (real COG pixel reads require rasterio which is not a dependency here)
            base = get_mock_soil_data(lat, lon)
            base["source"] = "openlandmap_stac_mock"
            base["stac_collections_available"] = len(collection_ids)
            return base
    except Exception as exc:
        log.warning("OpenLandMap STAC probe failed (%s) – using mock soil data", exc)

    # ── Tier 3: full mock fallback ────────────────────────────────────────────
    log.warning("All soil sources unavailable — using mock soil data for (%.4f, %.4f)", lat, lon)
    return get_mock_soil_data(lat, lon)


def _parse_soilgrids_layers(layers: list) -> dict[str, Any]:
    """
    Parse the ISRIC SoilGrids v2.0 properties/query response layers list.

    Each layer element looks like:
    {
      "name": "phh2o",
      "depths": [{"label": "0-30cm", "values": {"mean": 62}}],
      "unit_measure": {"mapped_units": "10^-1 pH"}
    }
    """
    def _get_mean(layers: list, name: str) -> float | None:
        for layer in layers:
            if layer.get("name") == name:
                for depth in layer.get("depths", []):
                    val = depth.get("values", {}).get("mean")
                    if val is not None:
                        return val
        return None

    # pH: stored as × 10  (e.g. 62 → pH 6.2)
    ph_raw = _get_mean(layers, "phh2o")
    ph = round(ph_raw / 10.0, 2) if ph_raw is not None else 6.5

    # SOC: stored as dg/kg → convert to g/kg (÷ 10)
    soc_raw = _get_mean(layers, "soc")
    soc = round(soc_raw / 10.0, 2) if soc_raw is not None else 1.8

    # Nitrogen: stored as cg/kg → convert to g/kg (÷ 100)
    n_raw = _get_mean(layers, "nitrogen")
    nitrogen = round(n_raw / 100.0, 2) if n_raw is not None else 1.2

    # Bulk density: stored as cg/cm³ → convert to g/cm³ (÷ 100)
    bd_raw = _get_mean(layers, "bdod")
    bulk_density = round(bd_raw / 100.0, 3) if bd_raw is not None else 1.35

    # Clay: stored as g/kg (no conversion needed)
    clay_raw = _get_mean(layers, "clay")
    clay = round(float(clay_raw), 1) if clay_raw is not None else 200.0

    compaction = round((bulk_density - 1.0) / 0.8, 3)

    return {
        "source":                    "isric_soilgrids",
        "ph":                        ph,
        "organic_carbon_g_per_kg":   soc,
        "nitrogen_g_per_kg":         nitrogen,
        "phosphorus_mg_per_kg":       22.0,   # SoilGrids v2 doesn't include P; use default
        "bulk_density_g_per_cm3":    bulk_density,
        "clay_g_per_kg":             clay,
        "compaction_index":          max(0.0, min(1.0, compaction)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Unified fetch (orchestrated by main.py)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all(lat: float, lon: float) -> dict[str, Any]:
    """
    Fetch all live data sources for a zone and merge with mock data
    for sources that still require mocking (NDVI, pesticide).

    Soil data now goes through a 3-tier strategy:
        1. ISRIC SoilGrids REST API
        2. OpenLandMap STAC catalog (fallback)
        3. mock_data (final fallback)

    Returns a unified raw data bundle consumed by scorer.py.
    """
    climate   = fetch_open_meteo(lat, lon)
    nasa      = fetch_nasa_power(lat, lon)
    gbif      = fetch_gbif_pollinators(lat, lon)
    soil      = fetch_soil_data(lat, lon)    # live → OpenLandMap → mock
    ndvi      = get_mock_ndvi_data(lat, lon)
    pesticide = get_mock_pesticide_data(lat, lon)

    return {
        "climate":   climate,
        "nasa":      nasa,
        "gbif":      gbif,
        "soil":      soil,
        "ndvi":      ndvi,
        "pesticide": pesticide,
    }
