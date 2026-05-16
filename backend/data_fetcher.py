
import logging
import re
import statistics
import time
from datetime import date, timedelta
from typing import Any

import requests

from config import (
    API_ENDPOINTS,
    AGROMONITORING_API_KEY,
    AGROMONITORING_IMAGE_WINDOW_DAYS,
    AGROMONITORING_MAX_CLOUD_PCT,
    AGROMONITORING_POLYGON_HALF_DEG,
    CLIMATE_LOOKBACK_DAYS,
    GBIF_MAX_RECORDS,
    GBIF_POLLINATOR_TAXON_KEYS,
    GBIF_RADIUS_KM,
    NASA_POWER_VARS,
    OPEN_METEO_VARS,
    REQUEST_TIMEOUT,
)
from mock_data import (
    compute_pesticide_proxy,
    get_mock_soil_data,
    get_mock_visitation_data,
)

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Fix 4: TTL cache (in-process dict, TTL = 300 s)
# ──────────────────────────────────────────────────────────────────────────────

_TTL_SECONDS = 300
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and time.monotonic() < entry[0]:
        log.debug("Cache HIT for %s", key)
        return entry[1]
    return None


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic() + _TTL_SECONDS, value)


# ──────────────────────────────────────────────────────────────────────────────
# Agromonitoring: polygon lifecycle + real NDVI/EVI satellite data  (Fix 9)
# ──────────────────────────────────────────────────────────────────────────────

_poly_id_cache: dict[str, str] = {}


def _get_or_create_polygon(lat: float, lon: float) -> str | None:
    """Return a polygon ID for (lat,lon), creating one if needed. None on failure."""
    if not AGROMONITORING_API_KEY:
        return None
    key = f"{lat:.4f}:{lon:.4f}"
    if key in _poly_id_cache:
        return _poly_id_cache[key]

    poly_name = f"polynexus-{key}"
    params = {"appid": AGROMONITORING_API_KEY}
    # Check existing polygons
    try:
        r = requests.get(API_ENDPOINTS["agromonitoring_polygons"], params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        for p in r.json():
            if p.get("name") == poly_name:
                _poly_id_cache[key] = p["id"]
                return p["id"]
    except Exception as exc:
        log.warning("[agro] GET polygons: %s", exc)

    # Build 1 km square GeoJSON and POST
    d = AGROMONITORING_POLYGON_HALF_DEG
    # GeoJSON exterior ring: counterclockwise (right-hand rule)
    ring = [[lon-d,lat-d],[lon+d,lat-d],[lon+d,lat+d],[lon-d,lat+d],[lon-d,lat-d]]
    body = {"name": poly_name, "geo_json": {"type":"Feature","properties":{},
            "geometry":{"type":"Polygon","coordinates":[ring]}}}
    try:
        r = requests.post(API_ENDPOINTS["agromonitoring_polygons"], params=params,
                          json=body, timeout=REQUEST_TIMEOUT)
        if r.status_code == 422:
            # Duplicate polygon: Agromonitoring returns the existing ID in the message
            msg = r.json().get("message", "")
            m = re.search(r"polygon '([0-9a-f]+)'", msg)
            if m:
                pid = m.group(1)
                _poly_id_cache[key] = pid
                log.info("[agro] reusing polygon %s (duplicate 422)", pid)
                return pid
        r.raise_for_status()
        pid = r.json()["id"]
        _poly_id_cache[key] = pid
        log.info("[agro] created polygon %s", pid)
        return pid
    except Exception as exc:
        log.warning("[agro] POST polygon: %s", exc)
        return None


def _fetch_ndvi_decline(poly_id: str) -> float:
    """12-week NDVI history decline rate. Returns 0.10 as neutral default."""
    import time as _t
    now = int(_t.time())
    try:
        r = requests.get(API_ENDPOINTS["agromonitoring_ndvi_history"],
            params={"appid":AGROMONITORING_API_KEY,"polyid":poly_id,
                    "start":now-84*86400,"end":now}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        hist = sorted(r.json(), key=lambda x: x.get("dt", 0))
        vals = [h["data"]["mean"] for h in hist if "data" in h and "mean" in h["data"]]
        if len(vals) < 4:
            return 0.10
        early = sum(vals[:4]) / 4
        late  = sum(vals[-4:]) / 4
        return round(max(0.0, min(0.9, (early - late) / max(early, 0.001))), 3)
    except Exception as exc:
        log.warning("[agro] NDVI history: %s", exc)
        return 0.10


def fetch_agromonitoring_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """Real satellite NDVI/EVI from Agromonitoring. Never returns random mock data."""
    cache_key = f"agro_ndvi:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    def _fallback(reason: str) -> dict[str, Any]:
        return {"source":"agromonitoring_unavailable","ndvi":0.45,"flowering_coverage":0.30,
                "patch_diversity":0.40,"hedgerow_density":0.20,"dead_wood_index":0.18,
                "bare_soil_fraction":0.25,"disturbance_score":0.30,"decline_rate_12w":0.10,
                "_fetch_error":reason}

    poly_id = _get_or_create_polygon(lat, lon)
    if not poly_id:
        return _fallback("no_polygon")

    import time as _t
    now = int(_t.time())
    params = {"appid":AGROMONITORING_API_KEY,"polyid":poly_id,
              "start":now-AGROMONITORING_IMAGE_WINDOW_DAYS*86400,"end":now}
    try:
        r = requests.get(API_ENDPOINTS["agromonitoring_image_search"], params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        images = r.json()
    except Exception as exc:
        log.warning("[agro] image/search: %s", exc)
        return _fallback(str(exc))

    if not images:
        return _fallback("no_images")

    best = min(
        (i for i in images if i.get("cl", 100) <= AGROMONITORING_MAX_CLOUD_PCT),
        key=lambda i: i.get("cl", 100), default=None
    ) or min(images, key=lambda i: i.get("cl", 100))

    ndvi_url = best.get("stats", {}).get("ndvi")
    evi_url  = best.get("stats", {}).get("evi")

    ndvi_mean = ndvi_std = ndvi_p25 = None
    if ndvi_url:
        try:
            s = requests.get(ndvi_url + f"?appid={AGROMONITORING_API_KEY}", timeout=REQUEST_TIMEOUT).json()
            ndvi_mean, ndvi_std, ndvi_p25 = s.get("mean"), s.get("std"), s.get("p25")
        except Exception as exc:
            log.warning("[agro] NDVI stats: %s", exc)

    if ndvi_mean is None:
        return _fallback("ndvi_stats_unavailable")

    evi_mean = 0.25
    if evi_url:
        try:
            evi_mean = requests.get(evi_url + f"?appid={AGROMONITORING_API_KEY}", timeout=REQUEST_TIMEOUT).json().get("mean", 0.25)
        except Exception as exc:
            log.warning("[agro] EVI stats: %s", exc)

    decline = _fetch_ndvi_decline(poly_id)
    p25 = ndvi_p25 if ndvi_p25 is not None else ndvi_mean * 0.75

    def _cl(v, lo=0.0, hi=1.0): return max(lo, min(hi, v))

    result = {
        "source":             "agromonitoring_satellite",
        "ndvi":               round(_cl(ndvi_mean), 3),
        "flowering_coverage": round(_cl((evi_mean - 0.10) / 0.50), 3),
        "patch_diversity":    round(_cl((ndvi_std or 0.15) * 3.5), 3),
        "hedgerow_density":   0.20,
        "dead_wood_index":    0.18,
        "bare_soil_fraction": round(_cl(1.0 - p25 - 0.20), 3),
        "disturbance_score":  round(_cl((0.50 - p25) * 1.20), 3),
        "decline_rate_12w":   decline,
        "satellite_type":     best.get("type", "unknown"),
        "cloud_pct":          best.get("cl"),
        "_fetch_error":       None,
    }
    _cache_set(cache_key, result)
    log.info("[agro] NDVI %.3f (%.4f,%.4f) %s", ndvi_mean, lat, lon, best.get("type"))
    return result



# ──────────────────────────────────────────────────────────────────────────────
# Date helpers
# ──────────────────────────────────────────────────────────────────────────────

def _date_range() -> tuple[str, str]:
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=CLIMATE_LOOKBACK_DAYS - 1)
    return start.isoformat(), end.isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# Open-Meteo  (Fix 1: isolated, Fix 4: cached)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_open_meteo(lat: float, lon: float) -> dict[str, Any]:
    cache_key = f"open_meteo:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    start_date, end_date = _date_range()
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_date, "end_date": end_date,
        "daily": ",".join(OPEN_METEO_VARS), "timezone": "UTC",
    }
    try:
        resp = requests.get(API_ENDPOINTS["open_meteo"], params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        daily = resp.json().get("daily", {})

        t_max  = [v for v in daily.get("temperature_2m_max", []) if v is not None]
        t_min  = [v for v in daily.get("temperature_2m_min", []) if v is not None]
        precip = [v for v in daily.get("precipitation_sum", []) if v is not None]
        wind   = [v for v in daily.get("wind_speed_10m_max",
                    daily.get("windspeed_10m_max", [])) if v is not None]
        etp    = [v for v in daily.get("et0_fao_evapotranspiration", []) if v is not None]

        t_mean = [(mx + mn) / 2 for mx, mn in zip(t_max, t_min)]
        total_precip = sum(precip)
        total_etp    = sum(etp)

        if total_etp == 0 and total_precip == 0:
            drought_index = None
        elif total_etp == 0:
            drought_index = 0.0
        else:
            drought_index = min(1.0, total_etp / max(total_precip, 1.0))

        result = {
            "source": "open_meteo",
            "temp_mean_c":            round(statistics.mean(t_mean), 2) if t_mean else 20.0,
            "temp_std_c":             round(statistics.stdev(t_mean), 3) if len(t_mean) > 1 else 0.0,
            "temp_max_c":             round(max(t_max), 2) if t_max else 30.0,
            "temp_min_c":             round(min(t_min), 2) if t_min else 10.0,
            "total_precipitation_mm": round(total_precip, 2),
            "avg_daily_precip_mm":    round(total_precip / max(len(precip), 1), 2),
            "precip_std_mm":          round(statistics.stdev(precip), 3) if len(precip) > 1 else 0.0,
            "avg_windspeed_kmh":      round(statistics.mean(wind), 2) if wind else 10.0,
            "drought_index":          round(drought_index, 3) if drought_index is not None else None,
            "days_fetched":           len(t_mean),
            "_fetch_error":           None,
        }
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        log.warning("[open_meteo] fetch failed (%s) — using mock", exc)
        fb = _mock_climate_fallback(lat, lon)
        fb["_fetch_error"] = str(exc)
        return fb


def _mock_climate_fallback(lat: float, lon: float) -> dict[str, Any]:
    base_temp = 25.0 - abs(lat) * 0.5
    return {
        "source": "mock_open_meteo",
        "temp_mean_c": round(base_temp, 2), "temp_std_c": 4.2,
        "temp_max_c": round(base_temp + 7, 2), "temp_min_c": round(base_temp - 7, 2),
        "total_precipitation_mm": 48.0, "avg_daily_precip_mm": 1.6,
        "precip_std_mm": 3.1, "avg_windspeed_kmh": 12.5,
        "drought_index": 0.38, "days_fetched": 0, "_fetch_error": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# NASA POWER  (Fix 1: isolated, Fix 4: cached)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_nasa_power(lat: float, lon: float) -> dict[str, Any]:
    cache_key = f"nasa_power:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    start_date, end_date = _date_range()
    params = {
        "parameters": ",".join(NASA_POWER_VARS), "community": "AG",
        "longitude": lon, "latitude": lat,
        "start": start_date.replace("-", ""), "end": end_date.replace("-", ""),
        "format": "JSON",
    }
    try:
        resp = requests.get(API_ENDPOINTS["nasa_power"], params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        props = resp.json().get("properties", {}).get("parameter", {})

        def _mean_valid(series: dict) -> float:
            vals = [v for v in series.values() if v not in (None, -999.0, -999)]
            return round(statistics.mean(vals), 4) if vals else 0.0

        result = {
            "source": "nasa_power",
            "root_zone_wetness": _mean_valid(props.get("GWETROOT", {})),
            "profile_wetness":   _mean_valid(props.get("GWETPROF", {})),
            "surface_temp_c":    _mean_valid(props.get("T2M", {})),
            "daily_precip_mm":   _mean_valid(props.get("PRECTOTCORR", {})),
            "_fetch_error": None,
        }
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        log.warning("[nasa_power] fetch failed (%s) — using mock", exc)
        return {
            "source": "mock_nasa_power",
            "root_zone_wetness": 0.45, "profile_wetness": 0.40,
            "surface_temp_c": 22.0, "daily_precip_mm": 1.8,
            "_fetch_error": str(exc),
        }


# ──────────────────────────────────────────────────────────────────────────────
# GBIF  (Fix 1: per-taxon isolation, Fix 4: cached)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_gbif_pollinators(lat: float, lon: float) -> dict[str, Any]:
    cache_key = f"gbif:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    all_species: set[str] = set()
    total_records = 0
    family_breakdown: dict[str, int] = {}
    taxon_errors: list[str] = []

    for taxon_key in GBIF_POLLINATOR_TAXON_KEYS:
        try:  # Fix 1: each taxon isolated independently
            params = {
                "taxonKey": taxon_key,
                "decimalLatitude":  f"{lat - _km_to_deg(GBIF_RADIUS_KM)},{lat + _km_to_deg(GBIF_RADIUS_KM)}",
                "decimalLongitude": f"{lon - _km_to_deg(GBIF_RADIUS_KM)},{lon + _km_to_deg(GBIF_RADIUS_KM)}",
                "limit": GBIF_MAX_RECORDS // len(GBIF_POLLINATOR_TAXON_KEYS),
                "hasCoordinate": "true", "occurrenceStatus": "PRESENT",
                "year": f"{date.today().year - 3},{date.today().year}",
            }
            resp = requests.get(API_ENDPOINTS["gbif_occurrences"], params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            total_records += len(results)
            for rec in results:
                sp = rec.get("species") or rec.get("scientificName")
                if sp:
                    all_species.add(sp)
                fam = rec.get("family", "Unknown")
                family_breakdown[fam] = family_breakdown.get(fam, 0) + 1
        except Exception as exc:
            log.warning("[gbif] taxon %s failed (%s) — skipping", taxon_key, exc)
            taxon_errors.append(f"taxon:{taxon_key}:{exc}")

    if total_records == 0:
        log.warning("[gbif] zero records — using mock fallback")
        fb = _mock_gbif_fallback(lat, lon)
        fb["_fetch_error"] = "; ".join(taxon_errors) if taxon_errors else "no_records"
        return fb

    result = {
        "source": "gbif", "species_count": len(all_species),
        "total_records": total_records, "family_breakdown": family_breakdown,
        "species_list": sorted(all_species)[:20],
        "_fetch_error": ("; ".join(taxon_errors) if taxon_errors else None),
    }
    _cache_set(cache_key, result)
    return result


def _km_to_deg(km: float) -> float:
    return km / 111.0


def _mock_gbif_fallback(lat: float, lon: float) -> dict[str, Any]:
    from mock_data import _zone_seed
    import math as _math
    s = _zone_seed(lat, lon)
    species_count = max(1, round(8 + _math.sin(s * 13.7) * 5))
    return {
        "source": "mock_gbif", "species_count": species_count,
        "total_records": species_count * 12,
        "family_breakdown": {"Apidae": species_count // 2, "Syrphidae": species_count // 3},
        "species_list": [f"mock_species_{i+1}" for i in range(min(species_count, 10))],
        "_fetch_error": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Soil  (Fix 1: per-tier isolation, Fix 4: cached)
# ──────────────────────────────────────────────────────────────────────────────

_SOILGRIDS_PROPS  = ["phh2o", "soc", "nitrogen", "bdod", "clay", "sand"]
_SOILGRIDS_DEPTHS = ["0-30cm"]


def fetch_soil_data(lat: float, lon: float) -> dict[str, Any]:
    cache_key = f"soil:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Tier 1: ISRIC SoilGrids
    try:
        resp = requests.get(
            API_ENDPOINTS["soilgrids"],
            params={"lat": lat, "lon": lon, "property": _SOILGRIDS_PROPS,
                    "depth": _SOILGRIDS_DEPTHS, "value": ["mean"]},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        layers = resp.json().get("properties", {}).get("layers", [])
        if layers:
            result = _parse_soilgrids_layers(layers)
            result["_fetch_error"] = None
            _cache_set(cache_key, result)
            return result
        log.warning("[soil] SoilGrids empty — trying OpenLandMap")
    except Exception as exc:
        log.warning("[soil] SoilGrids failed (%s) — trying OpenLandMap", exc)

    # Tier 2: OpenLandMap STAC
    try:
        resp = requests.get(API_ENDPOINTS["openlandmap_stac"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        links = resp.json().get("links", [])
        collection_ids = [l.get("title", "") for l in links if l.get("rel") in ("child", "item")]
        if collection_ids:
            base = get_mock_soil_data(lat, lon)
            base["source"] = "openlandmap_stac_mock"
            base["stac_collections_available"] = len(collection_ids)
            base["_fetch_error"] = None
            _cache_set(cache_key, base)
            return base
    except Exception as exc:
        log.warning("[soil] OpenLandMap failed (%s) — using mock", exc)

    # Tier 3: mock
    fb = get_mock_soil_data(lat, lon)
    fb["_fetch_error"] = "all_soil_sources_failed"
    return fb


def _parse_soilgrids_layers(layers: list) -> dict[str, Any]:
    def _get_mean(layers, name):
        for layer in layers:
            if layer.get("name") == name:
                for depth in layer.get("depths", []):
                    val = depth.get("values", {}).get("mean")
                    if val is not None:
                        return val
        return None

    ph_raw = _get_mean(layers, "phh2o")
    ph     = round(ph_raw / 10.0, 2) if ph_raw is not None else 6.5
    soc_raw = _get_mean(layers, "soc")
    soc     = round(soc_raw / 10.0, 2) if soc_raw is not None else 1.8
    n_raw    = _get_mean(layers, "nitrogen")
    nitrogen = round(n_raw / 100.0, 2) if n_raw is not None else 1.2
    bd_raw       = _get_mean(layers, "bdod")
    bulk_density = round(bd_raw / 100.0, 3) if bd_raw is not None else 1.35
    clay_raw = _get_mean(layers, "clay")
    clay     = round(float(clay_raw), 1) if clay_raw is not None else 200.0
    compaction = round((bulk_density - 1.0) / 0.8, 3)
    return {
        "source": "isric_soilgrids",
        "ph": ph, "organic_carbon_g_per_kg": soc,
        "nitrogen_g_per_kg": nitrogen, "phosphorus_mg_per_kg": 22.0,
        "bulk_density_g_per_cm3": bulk_density, "clay_g_per_kg": clay,
        "compaction_index": max(0.0, min(1.0, compaction)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Unified fetch
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# Fix 7: iNaturalist observations as real visitation signal
# ──────────────────────────────────────────────────────────────────────────────

_INAT_POLLINATOR_TAXA = [
    "Apidae",       # honey bees, bumble bees
    "Halictidae",   # sweat bees
    "Syrphidae",    # hoverflies
    "Nymphalidae",  # butterflies
    "Sphingidae",   # hawk moths
]
_INAT_LOOKBACK_DAYS = 84   # 12 weeks


def fetch_inat_observations(lat: float, lon: float, radius_km: float = 10.0) -> dict[str, Any]:
    """
    Fix 7: Query iNaturalist /v1/observations for recent pollinator sightings.
    Returns observation counts usable as a real visitation proxy.
    Falls back to modelled_visitation mock on failure.
    Fix 1: fully error-isolated.
    Fix 4: TTL cached.
    """
    cache_key = f"inat:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    from datetime import datetime, timezone
    cutoff = (date.today() - timedelta(days=_INAT_LOOKBACK_DAYS)).isoformat()
    base_url = "https://api.inaturalist.org/v1/observations"

    total_obs = 0
    weekly_counts: list[int] = [0] * 12
    taxon_breakdown: dict[str, int] = {}
    taxon_errors: list[str] = []

    for taxon in _INAT_POLLINATOR_TAXA:
        try:
            params = {
                "taxon_name":   taxon,
                "lat":          lat,
                "lng":          lon,
                "radius":       radius_km,
                "d1":           cutoff,
                "quality_grade": "research",
                "per_page":     200,
                "order":        "desc",
                "order_by":     "observed_on",
            }
            resp = requests.get(base_url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            taxon_breakdown[taxon] = len(results)
            total_obs += len(results)

            # Bin into 12-week buckets
            for rec in results:
                obs_date_str = rec.get("observed_on")
                if obs_date_str:
                    try:
                        obs_date = date.fromisoformat(obs_date_str)
                        days_ago = (date.today() - obs_date).days
                        week_idx = min(11, days_ago // 7)
                        weekly_counts[11 - week_idx] += 1
                    except ValueError:
                        pass

        except Exception as exc:
            log.warning("[inat] taxon %s failed (%s) — skipping", taxon, exc)
            taxon_errors.append(f"{taxon}:{exc}")

    if total_obs == 0:
        log.warning("[inat] zero observations — visitation will use modelled data")
        return {"source": "inat_no_data", "_fetch_error": "; ".join(taxon_errors) or "no_results"}

    # Convert weekly observation counts to a visits-per-hour proxy.
    # iNat obs ≠ actual visits, but the trend and ratio are meaningful.
    # Scale: assume 1 research-grade obs ≈ 3 unique visits (conservative).
    scale = 3.0 / (7 * 12)  # obs per day-week span → visits/hour approximation
    weekly_vph = [round(c * scale, 2) for c in weekly_counts]
    avg_vph    = round(sum(weekly_vph[-4:]) / 4, 2) if weekly_vph else 0.0
    expected   = round(sum(weekly_vph) / max(len(weekly_vph), 1) * 1.3, 2)  # baseline = historical mean * 1.3
    ratio      = round(avg_vph / expected, 3) if expected else 0.0

    # Estimate 12-week decline: compare first 4 vs last 4 weeks
    early_avg = sum(weekly_vph[:4]) / 4 if weekly_vph else 0.0
    late_avg  = sum(weekly_vph[-4:]) / 4 if weekly_vph else 0.0
    decline   = round(max(0.0, (early_avg - late_avg) / max(early_avg, 0.01)), 3)

    result = {
        "source":                        "inaturalist",
        "avg_visitations_per_hour":      avg_vph,
        "expected_visitations_per_hour": expected,
        "visitation_ratio":              ratio,
        "twelve_week_visits_per_hour":   weekly_vph,
        "decline_rate_12w":              decline,
        "pollination_timing_disruption": max(0.0, 1.0 - ratio),   # simple proxy
        "flowering_success_rate":        min(1.0, ratio * 0.85),  # conservative
        "recovery_volatility":           round(max(0.0, decline * 0.6), 3),
        "total_observations":            total_obs,
        "taxon_breakdown":               taxon_breakdown,
        "_fetch_error":                  ("; ".join(taxon_errors) if taxon_errors else None),
    }
    _cache_set(cache_key, result)
    log.info("[inat] %d observations for (%.4f, %.4f)", total_obs, lat, lon)
    return result


def fetch_all(lat: float, lon: float, zone_id: str = "") -> dict[str, Any]:  # type: ignore[override]
    """
    Unified fetch — Fix 7: tries iNaturalist for real visitation data;
    falls back to modelled mock only when iNat returns nothing.
    """
    climate   = fetch_open_meteo(lat, lon)
    nasa      = fetch_nasa_power(lat, lon)
    gbif      = fetch_gbif_pollinators(lat, lon)
    soil      = fetch_soil_data(lat, lon)
    # Fix 9: real satellite NDVI + state-statistics pesticide proxy
    ndvi      = fetch_agromonitoring_ndvi(lat, lon)
    pesticide = compute_pesticide_proxy(zone_id)

    # Fix 7: prefer iNaturalist; fall back to modelled
    inat = fetch_inat_observations(lat, lon)
    if inat.get("source") == "inaturalist":
        visitation = inat
    else:
        visitation = get_mock_visitation_data(lat, lon, ndvi, pesticide, climate, gbif)

    return {
        "climate": climate, "nasa": nasa, "gbif": gbif,
        "soil": soil, "ndvi": ndvi, "pesticide": pesticide,
        "visitation": visitation,
    }
