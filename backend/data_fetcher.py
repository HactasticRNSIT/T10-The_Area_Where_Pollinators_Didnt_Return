

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
# Unified fetch (orchestrated by main.py)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all(lat: float, lon: float) -> dict[str, Any]:
    """
    Fetch all live data sources for a zone and merge with mock data
    for sources that require mocking (SoilGrids, NDVI, pesticide).

    Returns a unified raw data bundle consumed by scorer.py.
    """
    climate   = fetch_open_meteo(lat, lon)
    nasa      = fetch_nasa_power(lat, lon)
    gbif      = fetch_gbif_pollinators(lat, lon)
    soil      = get_mock_soil_data(lat, lon)
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
