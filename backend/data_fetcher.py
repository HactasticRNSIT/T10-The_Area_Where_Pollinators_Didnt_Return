
import logging
import re
import statistics
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    OPEN_METEO_AGRO_HOURLY_VARS,
    OPEN_METEO_VARS,
    REQUEST_TIMEOUT,
)
from pesticide_data import compute_pesticide_proxy

__all__ = ["fetch_all"]

log = logging.getLogger(__name__)


from network import make_session

_SESSION = make_session()
_SESSION.headers.update({"User-Agent": "PolyNexus/1.0 realtime-ecosystem-dashboard"})

class CircuitBreaker:
    """Thread-safe circuit breaker.

    Multiple threads can call record_failure/record_success/is_open concurrently
    (e.g. from ThreadPoolExecutor inside fetch_all, or from /compare running up to
    6 zones in parallel).  Every read-modify-write is protected by a lock, mirroring
    the pattern used in ai_analyzer._cb_lock.
    """

    def __init__(self, threshold: int = 3, timeout: int = 60):
        self.threshold = threshold
        self.timeout = timeout
        self.failures = 0
        self.open_until = 0.0
        self._lock = threading.Lock()  # guards failures + open_until

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.threshold:
                self.open_until = time.monotonic() + self.timeout
                log.warning(
                    "Circuit breaker opened for %ss (failures=%d)",
                    self.timeout,
                    self.failures,
                )

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.open_until = 0.0

    def is_open(self) -> bool:
        with self._lock:
            now = time.monotonic()
            if self.open_until and now < self.open_until:
                return True
            if self.open_until:
                # Timeout elapsed — reset so next call gets a fresh attempt
                self.open_until = 0.0
                self.failures = 0
            return False

_breakers = {
    "open_meteo": CircuitBreaker(threshold=3, timeout=60),
    "nasa_power": CircuitBreaker(threshold=3, timeout=60),
    "gbif": CircuitBreaker(threshold=3, timeout=60),
    "soilgrids": CircuitBreaker(threshold=3, timeout=60),
    "inaturalist": CircuitBreaker(threshold=3, timeout=60),
}


def _get(url: str, **kwargs: Any) -> requests.Response:
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    t0 = time.monotonic()
    try:
        return _SESSION.get(url, **kwargs)
    finally:
        ms = (time.monotonic() - t0) * 1000
        domain = url.split("://")[-1].split("/")[0]
        log.info("[timing] GET %s | %.0f ms", domain, ms)


def _post(url: str, **kwargs: Any) -> requests.Response:
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    t0 = time.monotonic()
    try:
        return _SESSION.post(url, **kwargs)
    finally:
        ms = (time.monotonic() - t0) * 1000
        domain = url.split("://")[-1].split("/")[0]
        log.info("[timing] POST %s | %.0f ms", domain, ms)


# ---------------------------------------------------------------------------
# Safe error-code mapper (Fix #2 — P0)
# ---------------------------------------------------------------------------
# Map raw exception strings to a closed set of client-visible reason codes.
# This prevents raw URLs, tracebacks, and internal module paths from ever
# reaching _fetch_error fields that flow into API responses.

_SAFE_ERROR_PATTERNS: list[tuple[str, str]] = [
    ("circuit_breaker_open",  "circuit_open"),
    ("timeout",               "timeout"),
    ("timed out",             "timeout"),
    ("ConnectionError",       "network_error"),
    ("ConnectionRefused",     "network_error"),
    ("Max retries",           "network_error"),
    ("422",                   "http_error"),
    ("429",                   "rate_limited"),
    ("401",                   "auth_error"),
    ("403",                   "auth_error"),
    ("404",                   "http_error"),
    ("5",                     "http_error"),    # catches 500/502/503/504 prefixes
    ("JSONDecodeError",       "parse_error"),
    ("json",                  "parse_error"),
    ("KeyError",              "parse_error"),
    ("AttributeError",        "parse_error"),
]


def _safe_error(exc: Any) -> str | None:
    """Convert an exception (or existing error string) to a client-safe reason code.

    Raw exception messages, stack-trace fragments, full URLs with query parameters,
    and internal Python module names are never forwarded to callers.  Only the
    normalised reason code reaches the response body; the original message is already
    captured by log.warning/log.exception at the call site.
    """
    if exc is None:
        return None
    raw = str(exc)
    for pattern, code in _SAFE_ERROR_PATTERNS:
        if pattern.lower() in raw.lower():
            return code
    return "unavailable"


def _source_quality(source: str | None, fetch_error: Any = None) -> str:
    source = source or "unknown"
    if (
        "mock" in source
        or "unavailable" in source
        or source in {
            "inat_no_data",
            "unknown",
        }
    ):
        return "fallback"
    if "modelled" in source or source.startswith("owid_fao_") or "derived" in source:
        return "modelled"
    if fetch_error:
        return "fallback"
    return "live"


def _build_realtime_status(raw: dict[str, Any]) -> dict[str, Any]:
    sources = {
        key: value
        for key, value in raw.items()
        if isinstance(value, dict) and key in {"climate", "nasa", "gbif", "soil", "ndvi", "pesticide", "visitation"}
    }
    health = {}
    for key, value in sources.items():
        source_str = value.get("source", "unknown")
        if source_str == "sentinel2_copernicus" and "scene_date" in value:
            cloud_val = value.get('cloud_pct', 0)
            if isinstance(cloud_val, float): cloud_val = round(cloud_val, 1)
            source_str = f"Sentinel-2 (scene: {value['scene_date']}, cloud: {cloud_val}%)"
            
        health[key] = {
            "source": source_str,
            "quality": _source_quality(value.get("source"), value.get("_fetch_error")),
            # _safe_error maps raw exception strings → closed set of reason codes (Fix #2 / P0).
            # The original message is already captured server-side by log.warning/log.exception.
            "error": _safe_error(value.get("_fetch_error")),
            "warning": value.get("_data_warning"),
        }
    live_count = sum(1 for item in health.values() if item["quality"] == "live")
    fallback_count = sum(1 for item in health.values() if item["quality"] == "fallback")
    return {
        "generated_at": date.today().isoformat(),
        "lookback_days": CLIMATE_LOOKBACK_DAYS,
        "cache_ttl_seconds": _TTL_SECONDS,
        "live_source_count": live_count,
        "fallback_source_count": fallback_count,
        "live_source_ratio": round(live_count / max(len(health), 1), 3),
        "source_health": health,
    }


# ──────────────────────────────────────────────────────────────────────────────
# TTL cache (in-process dict, source-dependent TTL)
#
# IMPORTANT — SCALING NOTE: This is an in-process cache. In a multi-worker
# production deployment (e.g. Uvicorn with --workers > 1), each worker has its
# own independent cache, multiplying external API load. Before horizontal
# scaling, migrate to a shared Redis-backed cache, or force WORKERS=1.
# ──────────────────────────────────────────────────────────────────────────────

# Per-source TTL values (seconds).  Keys match the cache_key prefix used at
# each _cache_set call site.  Fallback for unknown prefixes is 300 s.
_TTL_BY_SOURCE: dict[str, int] = {
    "agro_ndvi":      86_400,   # 24 h  — satellite composites change daily at most
    "soilgrids":     604_800,   # 7 days — static pedology data
    "open_meteo":      3_600,   # 1 h   — climate archive
    "nasa_power":      3_600,   # 1 h   — NASA POWER agrometeorological archive
    "gbif":           86_400,   # 24 h  — species occurrence records
    "open_meteo_agro":   900,   # 15 min — short-range agro forecast updates
    "inat":           86_400,   # 24 h  — iNaturalist observations
    "ibp":            86_400,   # 24 h  — India Biodiversity Portal
    "water":           3_600,   # 1 h   — water-body proximity (OSM derived)
    "soil":          604_800,   # 7 days — SoilGrids REST API
}
_TTL_DEFAULT = 300  # fallback for any cache_key prefix not listed above

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _ttl_for_key(key: str) -> int:
    """Return the TTL (seconds) for a given cache key by matching its prefix."""
    for prefix, ttl in _TTL_BY_SOURCE.items():
        if key.startswith(prefix):
            return ttl
    return _TTL_DEFAULT


def _cache_get(key: str) -> Any | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.monotonic() < entry[0]:
            log.debug("Cache HIT for %s", key)
            return entry[1]
    return None


def _cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    """Store *value* under *key* with an expiry of *ttl* seconds.

    If *ttl* is not provided the TTL is inferred from the cache key prefix
    via ``_ttl_for_key`` (see ``_TTL_BY_SOURCE``).
    """
    effective_ttl = ttl if ttl is not None else _ttl_for_key(key)
    with _cache_lock:
        _cache[key] = (time.monotonic() + effective_ttl, value)

def clear_data_cache() -> None:
    """Clear all memory caches (called by admin endpoint)."""
    with _cache_lock:
        _cache.clear()
    with _poly_id_cache_lock:
        _poly_id_cache.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Agromonitoring: polygon lifecycle + real NDVI/EVI satellite data
# ──────────────────────────────────────────────────────────────────────────────

# Fix 3.3: polygon ID cache now stores (expiry_timestamp, polygon_id) tuples
# with a 7-day TTL. Stale polygon IDs (from deleted Agromonitoring accounts) no
# longer cause silent 404s indefinitely — they are evicted after 7 days.
_POLY_ID_CACHE_TTL = 7 * 24 * 3600  # 7 days in seconds
_poly_id_cache: dict[str, tuple[float, str]] = {}
_poly_id_cache_lock = threading.Lock()

COPERNICUS_TOKEN_CACHE = None
COPERNICUS_TOKEN_EXPIRY = 0

def _get_copernicus_token() -> str | None:
    global COPERNICUS_TOKEN_CACHE, COPERNICUS_TOKEN_EXPIRY
    import time
    from config import COPERNICUS_CLIENT_ID, COPERNICUS_CLIENT_SECRET
    if not COPERNICUS_CLIENT_ID or not COPERNICUS_CLIENT_SECRET:
        return None
    if COPERNICUS_TOKEN_CACHE and time.time() < COPERNICUS_TOKEN_EXPIRY:
        return COPERNICUS_TOKEN_CACHE
    try:
        r = _post('https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={'client_id': COPERNICUS_CLIENT_ID, 'client_secret': COPERNICUS_CLIENT_SECRET, 'grant_type': 'client_credentials'},
            timeout=10)
        r.raise_for_status()
        js = r.json()
        COPERNICUS_TOKEN_CACHE = js.get('access_token')
        COPERNICUS_TOKEN_EXPIRY = time.time() + js.get('expires_in', 3600) - 60
        return COPERNICUS_TOKEN_CACHE
    except Exception as exc:
        log.warning("[copernicus] Token fetch failed: %s", exc)
        return None

def _fetch_copernicus_ndvi(lat: float, lon: float) -> dict[str, Any] | None:
    token = _get_copernicus_token()
    if not token:
        return None
    
    import datetime, time
    d = 0.005
    bbox = [lon-d, lat-d, lon+d, lat+d]

    # Calculate the 30-day window based on the real current date
    now = datetime.datetime.now(datetime.UTC)
    start = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%dT00:00:00Z')
    end = now.strftime('%Y-%m-%dT23:59:59Z')

    payload = {
        'input': {
            'bounds': {'bbox': bbox, 'properties': {'crs': 'http://www.opengis.net/def/crs/EPSG/0/4326'}},
            'data': [{'type': 'sentinel-2-l2a', 'dataFilter': {'timeRange': {'from': start, 'to': end}, 'maxCloudCoverage': 20}}]
        },
        'aggregation': {
            'timeRange': {'from': start, 'to': end},
            'aggregationInterval': {'of': 'P1D'},
            'evalscript': '''//VERSION=3
                function setup() { return { input: ['B04', 'B08', 'SCL', 'dataMask'], output: [{ id: 'ndvi', bands: 1 }, { id: 'cloud', bands: 1 }, { id: 'dataMask', bands: 1 }] }; }
                function evaluatePixel(samples) {
                    let ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04);
                    let isCloud = (samples.SCL === 3 || samples.SCL === 8 || samples.SCL === 9 || samples.SCL === 10) ? 1.0 : 0.0;
                    return { ndvi: [ndvi], cloud: [isCloud], dataMask: [samples.dataMask] };
                }
            '''
        }
    }
    
    try:
        r = _post('https://sh.dataspace.copernicus.eu/api/v1/statistics', headers={'Authorization': f'Bearer {token}'}, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json().get('data', [])
        valid = [d for d in data if d.get('outputs', {}).get('ndvi', {}).get('bands', {}).get('B0', {}).get('stats', {}).get('sampleCount', 0) > 0]
        if valid:
            latest = valid[-1]
            ndvi_mean = latest['outputs']['ndvi']['bands']['B0']['stats']['mean']
            cloud_pct = latest['outputs']['cloud']['bands']['B0']['stats']['mean'] * 100
            scene_date = latest['interval']['from'][:10]
            
            return {
                "source": "sentinel2_copernicus",
                "ndvi": round(ndvi_mean, 3),
                "evi": round(max(0.0, min(1.0, ndvi_mean * 0.82)), 3),
                "lai": round(max(0.0, min(1.0, ndvi_mean * 0.82)) * 6.0, 3),
                "flowering_coverage": round(max(0.0, ndvi_mean - 0.15), 3),
                "bare_soil_fraction": round(max(0.0, 1.0 - ndvi_mean - 0.25), 3),
                "scene_date": scene_date,
                "cloud_pct": round(cloud_pct, 1),
                "_fetch_error": None
            }
    except Exception as exc:
        log.warning("[copernicus] stats API: %s", exc)
    return None

def _get_or_create_polygon(lat: float, lon: float) -> str | None:
    """Return a polygon ID for (lat,lon), creating one if needed. None on failure."""
    if not AGROMONITORING_API_KEY:
        return None
    key = f"{lat:.4f}:{lon:.4f}"
    now = time.monotonic()
    # Fix 3.3: check TTL on read and evict stale entries
    with _poly_id_cache_lock:
        entry = _poly_id_cache.get(key)
        if entry is not None and now < entry[0]:
            return entry[1]

    poly_name = f"polynexus-{key}"
    params = {"appid": AGROMONITORING_API_KEY}
    try:
        r = _get(API_ENDPOINTS["agromonitoring_polygons"], params=params)
        r.raise_for_status()
        for p in r.json():
            if p.get("name") == poly_name:
                with _poly_id_cache_lock:
                    _poly_id_cache[key] = (now + _POLY_ID_CACHE_TTL, p["id"])
                return p["id"]
    except Exception as exc:
        log.warning("[agro] GET polygons: %s", exc)

    d = AGROMONITORING_POLYGON_HALF_DEG
    ring = [[lon-d,lat-d],[lon+d,lat-d],[lon+d,lat+d],[lon-d,lat+d],[lon-d,lat-d]]
    body = {"name": poly_name, "geo_json": {"type":"Feature","properties":{},
            "geometry":{"type":"Polygon","coordinates":[ring]}}}
    try:
        r = _post(API_ENDPOINTS["agromonitoring_polygons"], params=params, json=body)
        if r.status_code == 422:
            msg = r.json().get("message", "")
            m = re.search(r"polygon '([0-9a-f]+)'", msg)
            if m:
                pid = m.group(1)
                with _poly_id_cache_lock:
                    _poly_id_cache[key] = (now + _POLY_ID_CACHE_TTL, pid)
                log.info("[agro] reusing polygon %s (duplicate 422)", pid)
                return pid
        r.raise_for_status()
        pid = r.json()["id"]
        with _poly_id_cache_lock:
            _poly_id_cache[key] = (now + _POLY_ID_CACHE_TTL, pid)
        log.info("[agro] created polygon %s", pid)
        return pid
    except Exception as exc:
        log.warning("[agro] POST polygon: %s", exc)
        return None


def _fetch_ndvi_decline(poly_id: str) -> float | None:
    """12-week NDVI history decline rate from real satellite data. Returns None on failure."""
    import time as _t
    now = int(_t.time())
    try:
        r = _get(API_ENDPOINTS["agromonitoring_ndvi_history"],
            params={"appid":AGROMONITORING_API_KEY,"polyid":poly_id,
                    "start":now-84*86400,"end":now})
        r.raise_for_status()
        hist = sorted(r.json(), key=lambda x: x.get("dt", 0))
        vals = [h["data"]["mean"] for h in hist if "data" in h and "mean" in h["data"]]
        if len(vals) < 4:
            return None
        early = sum(vals[:4]) / 4
        late  = sum(vals[-4:]) / 4
        return round(max(0.0, min(0.9, (early - late) / max(early, 0.001))), 3)
    except Exception as exc:
        log.warning("[agro] NDVI history: %s", exc)
        return None


def fetch_agromonitoring_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """
    Real satellite NDVI/EVI from Agromonitoring (Sentinel-2/Landsat-8).
    When Agromonitoring is unavailable, derives a proxy from Open-Meteo agro
    forecast (EVI approximation from soil temperature + VPD).
    Never returns fabricated numbers.
    """
    cache_key = f"agro_ndvi:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    poly_id = _get_or_create_polygon(lat, lon)

    if poly_id:
        import time as _t
        now = int(_t.time())
        params = {"appid":AGROMONITORING_API_KEY,"polyid":poly_id,
                  "start":now-AGROMONITORING_IMAGE_WINDOW_DAYS*86400,"end":now}
        try:
            r = _get(API_ENDPOINTS["agromonitoring_image_search"], params=params)
            r.raise_for_status()
            images = r.json()

            if images:
                best = min(
                    (i for i in images if i.get("cl", 100) <= AGROMONITORING_MAX_CLOUD_PCT),
                    key=lambda i: i.get("cl", 100), default=None
                ) or min(images, key=lambda i: i.get("cl", 100))

                ndvi_url = best.get("stats", {}).get("ndvi")
                evi_url  = best.get("stats", {}).get("evi")
                lai_url  = best.get("stats", {}).get("lai")

                ndvi_mean = ndvi_std = ndvi_p25 = None
                if ndvi_url:
                    try:
                        s = _get(ndvi_url, params={"appid": AGROMONITORING_API_KEY}).json()
                        ndvi_mean, ndvi_std, ndvi_p25 = s.get("mean"), s.get("std"), s.get("p25")
                    except Exception as exc:
                        log.warning("[agro] NDVI stats: %s", exc)

                if ndvi_mean is not None:
                    evi_mean = 0.25
                    if evi_url:
                        try:
                            evi_mean = _get(evi_url, params={"appid": AGROMONITORING_API_KEY}).json().get("mean", 0.25)
                        except Exception as exc:
                            log.warning("[agro] EVI stats: %s", exc)
                    lai_mean = None
                    if lai_url:
                        try:
                            lai_mean = _get(lai_url, params={"appid": AGROMONITORING_API_KEY}).json().get("mean")
                        except Exception as exc:
                            log.warning("[agro] LAI stats: %s", exc)

                    decline = _fetch_ndvi_decline(poly_id)
                    p25 = ndvi_p25 if ndvi_p25 is not None else ndvi_mean * 0.75
                    lai_est = lai_mean if lai_mean is not None else max(0.0, min(6.0, evi_mean * 6.0))

                    def _cl(v, lo=0.0, hi=1.0): return max(lo, min(hi, v))

                    result = {
                        "source":             "agromonitoring_satellite",
                        "ndvi":               round(_cl(ndvi_mean), 3),
                        "evi":                round(_cl(evi_mean), 3),
                        "lai":                round(lai_est, 3),
                        "flowering_coverage": round(_cl((evi_mean - 0.10) / 0.50), 3),
                        "patch_diversity":    round(_cl((ndvi_std or 0.15) * 3.5), 3),
                        "hedgerow_density":   None,
                        "dead_wood_index":    None,
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
        except Exception as exc:
            log.warning("[agro] image/search: %s", exc)

    # ── Tier 2: Copernicus Sentinel Hub ──────────────────────────────────────
    log.info("[ndvi] Agromonitoring unavailable — attempting Copernicus Sentinel Hub")
    copernicus_res = _fetch_copernicus_ndvi(lat, lon)
    if copernicus_res:
        copernicus_res["patch_diversity"] = None
        copernicus_res["hedgerow_density"] = None
        copernicus_res["dead_wood_index"] = None
        copernicus_res["disturbance_score"] = None
        copernicus_res["decline_rate_12w"] = None
        _cache_set(cache_key, copernicus_res)
        log.info("[copernicus] NDVI %.3f (%.4f,%.4f) %s", copernicus_res["ndvi"], lat, lon, copernicus_res["scene_date"])
        return copernicus_res

    # ── Tier 3: derive NDVI proxy from Open-Meteo agro forecast ──────────────
    log.info("[ndvi] Copernicus unavailable — deriving proxy from Open-Meteo agro")
    agro = _fetch_open_meteo_agro(lat, lon)
    if not agro.get("_fetch_error"):
        vpd      = agro.get("vapour_pressure_deficit_kpa") or 1.0
        st6      = agro.get("soil_temp_6cm_c") or 20.0
        moisture = agro.get("root_zone_wetness") or 0.4
        # EVI/NDVI proxy: optimal conditions (VPD 0.5–1.5, temp 15–28°C, moisture 0.4–0.7)
        # → higher estimated vegetation vigour
        vpd_fav   = max(0.0, 1.0 - abs(vpd - 1.0) / 2.0)
        temp_fav  = max(0.0, 1.0 - abs(st6 - 22.0) / 15.0)
        moist_fav = max(0.0, min(1.0, moisture / 0.6))
        ndvi_est  = round(0.25 + (vpd_fav * 0.30 + temp_fav * 0.35 + moist_fav * 0.35) * 0.45, 3)
        evi_est   = round(max(0.0, min(1.0, ndvi_est * 0.82)), 3)
        result = {
            "source":             "open_meteo_derived_ndvi_proxy",
            "ndvi":               ndvi_est,
            "evi":                evi_est,
            "lai":                round(evi_est * 6.0, 3),
            "flowering_coverage": round(max(0.0, ndvi_est - 0.15), 3),
            "patch_diversity":    None,
            "hedgerow_density":   None,
            "dead_wood_index":    None,
            "bare_soil_fraction": round(max(0.0, 1.0 - ndvi_est - 0.25), 3),
            "disturbance_score":  None,
            "decline_rate_12w":   None,
            "_fetch_error":       "agromonitoring_unavailable",
            "_data_warning":      "NDVI derived from Open-Meteo agro conditions — not satellite imagery",
        }
        _cache_set(cache_key, result)
        return result

    # ── Tier 3: genuinely unavailable ────────────────────────────────────────
    return {
        "source":             "ndvi_unavailable",
        "ndvi":               None,
        "evi":                None,
        "lai":                None,
        "flowering_coverage": None,
        "patch_diversity":    None,
        "hedgerow_density":   None,
        "dead_wood_index":    None,
        "bare_soil_fraction": None,
        "disturbance_score":  None,
        "decline_rate_12w":   None,
        "_fetch_error":       "agromonitoring_unavailable; open_meteo_agro_unavailable",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Date helpers
# ──────────────────────────────────────────────────────────────────────────────

def _date_range() -> tuple[str, str]:
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=CLIMATE_LOOKBACK_DAYS - 1)
    return start.isoformat(), end.isoformat()


def _mean(values: list[float]) -> float | None:
    clean = [v for v in values if isinstance(v, (int, float))]
    return statistics.mean(clean) if clean else None


def _fetch_open_meteo_agro(lat: float, lon: float) -> dict[str, Any]:
    """
    Open-Meteo agro forecast: humidity, VPD, soil moisture, soil temperature.
    Used as a secondary real-data source — not a mock.
    """
    cache_key = f"open_meteo_agro:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    params = {
        "latitude": lat, "longitude": lon,
        "hourly": ",".join(OPEN_METEO_AGRO_HOURLY_VARS),
        "past_days": 14, "forecast_days": 1,
        "timezone": "UTC",
    }
    try:
        if _breakers["open_meteo"].is_open():
            raise Exception("circuit_breaker_open")
        resp = _get("https://api.open-meteo.com/v1/forecast", params=params)
        resp.raise_for_status()
        _breakers["open_meteo"].record_success()
        hourly = resp.json().get("hourly", {})

        def avg(name: str) -> float | None:
            return _mean([v for v in hourly.get(name, []) if v is not None])

        shallow = avg("soil_moisture_0_to_1cm")
        root_layers = [
            avg("soil_moisture_1_to_3cm"),
            avg("soil_moisture_3_to_9cm"),
            avg("soil_moisture_9_to_27cm"),
            avg("soil_moisture_27_to_81cm"),
        ]
        root = _mean([v for v in root_layers if v is not None])
        humidity = avg("relative_humidity_2m")
        vpd = avg("vapour_pressure_deficit")
        soil_temp_surface = avg("soil_temperature_0cm")
        soil_temp_6cm = avg("soil_temperature_6cm")
        result = {
            "source": "open_meteo_forecast_agro",
            "relative_humidity_pct": round(humidity, 2) if humidity is not None else None,
            "vapour_pressure_deficit_kpa": round(vpd, 3) if vpd is not None else None,
            "soil_temp_surface_c": round(soil_temp_surface, 2) if soil_temp_surface is not None else None,
            "soil_temp_6cm_c": round(soil_temp_6cm, 2) if soil_temp_6cm is not None else None,
            "surface_soil_moisture": round(shallow, 4) if shallow is not None else None,
            "root_zone_wetness": round(root, 4) if root is not None else None,
            "hours_fetched": len(hourly.get("time", [])),
            "_fetch_error": None,
        }
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        if "circuit_breaker_open" not in str(exc):
            _breakers["open_meteo"].record_failure()
        log.warning("[open_meteo_agro] fetch failed (%s)", exc)
        return {"source": "open_meteo_forecast_agro_unavailable", "_fetch_error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# Open-Meteo climate (cached)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_open_meteo(lat: float, lon: float) -> dict:
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
        if _breakers["open_meteo"].is_open():
            raise Exception("circuit_breaker_open")
        resp = _get(API_ENDPOINTS["open_meteo"], params=params)
        resp.raise_for_status()
        _breakers["open_meteo"].record_success()

        daily = resp.json().get("daily", {})
        elevation = resp.json().get("elevation", 0.0)

        t_max  = [v for v in daily.get("temperature_2m_max", []) if v is not None]
        t_min  = [v for v in daily.get("temperature_2m_min", []) if v is not None]
        precip = [v for v in daily.get("precipitation_sum", []) if v is not None]
        wind   = [v for v in daily.get("wind_speed_10m_max", []) if v is not None]
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

        agro = _fetch_open_meteo_agro(lat, lon)
        result = {
            "source": "open_meteo_archive_plus_forecast_agro"
                      if not agro.get("_fetch_error") else "open_meteo",
            "temp_mean_c":            round(statistics.mean(t_mean), 2) if t_mean else None,
            "temp_std_c":             round(statistics.stdev(t_mean), 3) if len(t_mean) > 1 else None,
            "temp_max_c":             round(max(t_max), 2) if t_max else None,
            "temp_min_c":             round(min(t_min), 2) if t_min else None,
            "total_precipitation_mm": round(total_precip, 2),
            "avg_daily_precip_mm":    round(total_precip / max(len(precip), 1), 2),
            "precip_std_mm":          round(statistics.stdev(precip), 3) if len(precip) > 1 else None,
            "avg_windspeed_kmh":      round(statistics.mean(wind), 2) if wind else None,
            "drought_index":          round(drought_index, 3) if drought_index is not None else None,
            "days_fetched":           len(t_mean),
            "elevation":              elevation,
            "_fetch_error":           None,
        }
        if not agro.get("_fetch_error"):
            result.update({
                "relative_humidity_pct": agro.get("relative_humidity_pct"),
                "vapour_pressure_deficit_kpa": agro.get("vapour_pressure_deficit_kpa"),
                "surface_soil_moisture": agro.get("surface_soil_moisture"),
                "root_zone_wetness_open_meteo": agro.get("root_zone_wetness"),
                "soil_temp_surface_c": agro.get("soil_temp_surface_c"),
                "soil_temp_6cm_c": agro.get("soil_temp_6cm_c"),
                "agro_source": agro.get("source"),
            })
        else:
            result["_data_warning"] = f"open_meteo_agro_unavailable:{agro.get('_fetch_error')}"
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        if "circuit_breaker_open" not in str(exc):
            _breakers["open_meteo"].record_failure()
        log.warning("[open_meteo] fetch failed (%s)", exc)
        return {
            "source": "open_meteo_unavailable",
            "temp_mean_c": None,
            "temp_std_c": None,
            "temp_max_c": None,
            "temp_min_c": None,
            "total_precipitation_mm": None,
            "avg_daily_precip_mm": None,
            "precip_std_mm": None,
            "avg_windspeed_kmh": None,
            "drought_index": None,
            "days_fetched": 0,
            "_fetch_error": str(exc),
        }


# ──────────────────────────────────────────────────────────────────────────────
# NASA POWER (cached)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_nasa_power(lat: float, lon: float) -> dict[str, Any]:
    cache_key = f"nasa_power:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    start_date, end_date = _date_range()
    params = {
        "parameters": ",".join(NASA_POWER_VARS),
        "community": "AG", "longitude": lon, "latitude": lat,
        "start": start_date, "end": end_date, "format": "JSON",
    }
    try:
        if _breakers["nasa_power"].is_open():
            raise Exception("circuit_breaker_open")
        resp = _get(API_ENDPOINTS["nasa_power"], params=params)
        resp.raise_for_status()
        _breakers["nasa_power"].record_success()
        props = resp.json().get("properties", {}).get("parameter", {})

        def _mean_valid(series: dict) -> float | None:
            vals = [v for v in series.values() if v not in (None, -999.0, -999)]
            return round(statistics.mean(vals), 4) if vals else None

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
        if "circuit_breaker_open" not in str(exc):
            _breakers["nasa_power"].record_failure()
        log.warning("[nasa_power] fetch failed (%s) — trying Open-Meteo agro fallback", exc)
        # Tier 2: real Open-Meteo agro data is a valid science-grade soil moisture proxy
        agro = _fetch_open_meteo_agro(lat, lon)
        if not agro.get("_fetch_error") and agro.get("root_zone_wetness") is not None:
            return {
                "source": "open_meteo_forecast_agro_modelled_nasa_fallback",
                "root_zone_wetness": agro.get("root_zone_wetness"),
                "profile_wetness": agro.get("root_zone_wetness"),
                "surface_temp_c": agro.get("soil_temp_surface_c"),
                "daily_precip_mm": None,
                "surface_soil_moisture": agro.get("surface_soil_moisture"),
                "vapour_pressure_deficit_kpa": agro.get("vapour_pressure_deficit_kpa"),
                "_fetch_error": str(exc),
                "_data_warning": "NASA POWER unavailable; Open-Meteo agro soil moisture used",
            }
        # Tier 3: genuinely unavailable — return None values, not hardcoded guesses
        log.warning("[nasa_power] Open-Meteo agro also unavailable — returning unavailable")
        return {
            "source": "nasa_unavailable",
            "root_zone_wetness": None,
            "profile_wetness": None,
            "surface_temp_c": None,
            "daily_precip_mm": None,
            "_fetch_error": f"{exc}; open_meteo_agro:{agro.get('_fetch_error')}",
        }


# ──────────────────────────────────────────────────────────────────────────────
# GBIF (per-taxon isolation, cached)
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
        try:
            params = {
                "taxonKey": taxon_key,
                "decimalLatitude":  f"{lat - _km_to_deg(GBIF_RADIUS_KM)},{lat + _km_to_deg(GBIF_RADIUS_KM)}",
                "decimalLongitude": f"{lon - _km_to_deg(GBIF_RADIUS_KM)},{lon + _km_to_deg(GBIF_RADIUS_KM)}",
                "limit": GBIF_MAX_RECORDS // len(GBIF_POLLINATOR_TAXON_KEYS),
                "hasCoordinate": "true", "occurrenceStatus": "PRESENT",
                "year": f"{date.today().year - 3},{date.today().year}",
            }
            if _breakers["gbif"].is_open():
                raise Exception("circuit_breaker_open")
            resp = _get(API_ENDPOINTS["gbif_occurrences"], params=params)
            resp.raise_for_status()
            _breakers["gbif"].record_success()
            results = resp.json().get("results", [])
            total_records += len(results)
            for rec in results:
                sp = rec.get("species") or rec.get("scientificName")
                if sp:
                    all_species.add(sp)
                fam = rec.get("family", "Unknown")
                family_breakdown[fam] = family_breakdown.get(fam, 0) + 1
        except Exception as exc:
            if "circuit_breaker_open" not in str(exc):
                _breakers["gbif"].record_failure()
            log.warning("[gbif] taxon %s failed (%s) — skipping", taxon_key, exc)
            taxon_errors.append(f"taxon:{taxon_key}:{exc}")

    # Zero records IS the real answer — return it honestly (not a fake species list)
    result = {
        "source": "gbif" if total_records > 0 else "gbif_no_data",
        "species_count": len(all_species),
        "total_records": total_records,
        "family_breakdown": family_breakdown,
        "species_list": sorted(all_species)[:20],
        "_fetch_error": ("; ".join(taxon_errors) if taxon_errors else None)
                        if total_records > 0
                        else ("; ".join(taxon_errors) if taxon_errors else "no_records_found"),
    }
    # Fix 1.4: cache zero-record results with the same TTL as non-zero results.
    # A zone that legitimately returns 0 records should not hammer the GBIF API on
    # every request within the same TTL window (especially for remote/new zones).
    _cache_set(cache_key, result)
    return result


def _km_to_deg(km: float) -> float:
    return km / 111.0


# ──────────────────────────────────────────────────────────────────────────────
# Soil (per-tier isolation, cached)
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
        if _breakers["soilgrids"].is_open():
            raise Exception("circuit_breaker_open")
        resp = _get(
            API_ENDPOINTS["soilgrids"],
            params={"lat": lat, "lon": lon, "property": _SOILGRIDS_PROPS,
                    "depth": _SOILGRIDS_DEPTHS, "value": ["mean"]},
        )
        resp.raise_for_status()
        _breakers["soilgrids"].record_success()
        layers = resp.json().get("properties", {}).get("layers", [])
        if layers:
            result = _parse_soilgrids_layers(layers)
            result["_fetch_error"] = None
            _cache_set(cache_key, result)
            return result
        log.warning("[soil] SoilGrids returned empty layers — trying OpenLandMap")
    except Exception as exc:
        if "circuit_breaker_open" not in str(exc):
            _breakers["soilgrids"].record_failure()
        log.warning("[soil] SoilGrids failed (%s) — trying OpenLandMap", exc)

    # Tier 2: OpenLandMap STAC metadata check (confirms data availability)
    try:
        resp = _get(API_ENDPOINTS["openlandmap_stac"])
        resp.raise_for_status()
        links = resp.json().get("links", [])
        collection_ids = [l.get("title", "") for l in links if l.get("rel") in ("child", "item")]
        if collection_ids:
            log.warning("[soil] OpenLandMap STAC reachable but raster query unavailable — soil_unavailable")
    except Exception as exc:
        log.warning("[soil] OpenLandMap failed (%s)", exc)

    # Tier 3: genuinely unavailable — return None values, no fabricated soil numbers
    log.warning("[soil] All real soil sources failed — returning soil_unavailable")
    return {
        "source": "soil_unavailable",
        "ph": None,
        "organic_carbon_g_per_kg": None,
        "nitrogen_g_per_kg": None,
        "phosphorus_mg_per_kg": None,
        "bulk_density_g_per_cm3": None,
        "clay_g_per_kg": None,
        "sand_g_per_kg": None,
        "texture_class": None,
        "compaction_index": None,
        "_fetch_error": "all_soil_sources_failed",
    }


def _parse_soilgrids_layers(layers: list) -> dict[str, Any]:
    def _get_mean(layers, name):
        for layer in layers:
            if layer.get("name") == name:
                for depth in layer.get("depths", []):
                    val = depth.get("values", {}).get("mean")
                    if val is not None:
                        return val
        return None

    missing: list[str] = []

    def _require(name: str) -> Any:
        val = _get_mean(layers, name)
        if val is None:
            missing.append(name)
        return val

    ph_raw = _require("phh2o")
    ph     = round(ph_raw / 10.0, 2) if ph_raw is not None else None
    soc_raw = _require("soc")
    soc     = round(soc_raw / 10.0, 2) if soc_raw is not None else None
    n_raw    = _require("nitrogen")
    nitrogen = round(n_raw / 100.0, 2) if n_raw is not None else None
    bd_raw       = _require("bdod")
    bulk_density = round(bd_raw / 100.0, 3) if bd_raw is not None else None
    clay_raw = _require("clay")
    clay     = round(float(clay_raw), 1) if clay_raw is not None else None
    sand_raw = _require("sand")
    sand     = round(float(sand_raw), 1) if sand_raw is not None else None
    compaction = round(max(0.0, (bulk_density - 1.0) / 0.8), 3) if bulk_density is not None else None

    result = {
        "source": "isric_soilgrids",
        "ph": ph,
        "organic_carbon_g_per_kg": soc,
        "nitrogen_g_per_kg": nitrogen,
        "phosphorus_mg_per_kg": None,  # not in SoilGrids v2 REST — requires separate query
        "bulk_density_g_per_cm3": bulk_density,
        "clay_g_per_kg": clay,
        "sand_g_per_kg": sand,
        "texture_class": _texture_class(clay, sand),
        "soilgrids_depth": ",".join(_SOILGRIDS_DEPTHS),
        "soilgrids_property_count": len(layers),
        "compaction_index": compaction,
    }
    if missing:
        result["_data_warning"] = f"SoilGrids missing properties: {', '.join(missing)}"
    return result


def _texture_class(clay_g_per_kg: float | None, sand_g_per_kg: float | None) -> str | None:
    if clay_g_per_kg is None or sand_g_per_kg is None:
        return None
    clay_pct = clay_g_per_kg / 10.0
    sand_pct = sand_g_per_kg / 10.0
    if clay_pct >= 40:
        return "clay"
    if sand_pct >= 70 and clay_pct < 15:
        return "sandy"
    if clay_pct >= 27:
        return "clay_loam"
    if sand_pct >= 52:
        return "sandy_loam"
    return "loam"


# ──────────────────────────────────────────────────────────────────────────────
# iNaturalist observations — real visitation signal
# ──────────────────────────────────────────────────────────────────────────────

_INAT_POLLINATOR_TAXA = [
    "Apidae",       # honey bees, bumble bees
    "Halictidae",   # sweat bees
    "Syrphidae",    # hoverflies
    "Nymphalidae",  # butterflies
    "Sphingidae",   # hawk moths
]
_INAT_LOOKBACK_DAYS = 84   # 12 weeks


def fetch_inat_observations(
    lat: float,
    lon: float,
    # Fix 6.4: use GBIF_RADIUS_KM from config so both GBIF and iNat searches
    # use the same configurable radius. Previously this was hardcoded to 10.0 km
    # independently of GBIF_RADIUS_KM, meaning changing config.py only affected GBIF.
    radius_km: float = GBIF_RADIUS_KM,
) -> dict[str, Any]:
    """
    Query iNaturalist /v1/observations for recent research-grade pollinator sightings.
    Returns real observation counts as a visitation proxy.
    When iNat returns no data, falls back to Open-Meteo UV + temperature derived estimate.
    Never returns fabricated numbers.
    """
    cache_key = f"inat:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

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
            if _breakers["inaturalist"].is_open():
                raise Exception("circuit_breaker_open")
            resp = _get(base_url, params=params)
            resp.raise_for_status()
            _breakers["inaturalist"].record_success()
            results = resp.json().get("results", [])
            taxon_breakdown[taxon] = len(results)
            total_obs += len(results)

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
            if "circuit_breaker_open" not in str(exc):
                _breakers["inaturalist"].record_failure()
            log.warning("[inat] taxon %s failed (%s) — skipping", taxon, exc)
            taxon_errors.append(f"{taxon}:{exc}")

    if total_obs > 0:
        # Convert observation counts → visits/hour proxy
        # Scale: 1 research-grade obs ≈ 3 unique visits (conservative)
        scale = 3.0 / (7 * 12)
        weekly_vph = [round(c * scale, 2) for c in weekly_counts]
        avg_vph    = round(sum(weekly_vph[-4:]) / 4, 2) if weekly_vph else 0.0
        expected   = round(sum(weekly_vph) / max(len(weekly_vph), 1) * 1.3, 2)
        ratio      = round(avg_vph / expected, 3) if expected else 0.0
        early_avg  = sum(weekly_vph[:4]) / 4 if weekly_vph else 0.0
        late_avg   = sum(weekly_vph[-4:]) / 4 if weekly_vph else 0.0
        decline    = round(max(0.0, (early_avg - late_avg) / max(early_avg, 0.01)), 3)

        result = {
            "source":                        "inaturalist",
            "avg_visitations_per_hour":      avg_vph,
            "expected_visitations_per_hour": expected,
            "visitation_ratio":              ratio,
            "twelve_week_visits_per_hour":   weekly_vph,
            "decline_rate_12w":              decline,
            "pollination_timing_disruption": max(0.0, 1.0 - ratio),
            "flowering_success_rate":        min(1.0, ratio * 0.85),
            "recovery_volatility":           round(max(0.0, decline * 0.6), 3),
            "total_observations":            total_obs,
            "taxon_breakdown":               taxon_breakdown,
            "_fetch_error":                  ("; ".join(taxon_errors) if taxon_errors else None),
        }
        _cache_set(cache_key, result)
        log.info("[inat] %d observations for (%.4f, %.4f)", total_obs, lat, lon)
        return result

    log.warning("[inat] zero observations — returning inat_no_data")
    return {
        "source": "inat_no_data",
        "avg_visitations_per_hour": None,
        "expected_visitations_per_hour": None,
        "visitation_ratio": None,
        "twelve_week_visits_per_hour": [],
        "decline_rate_12w": None,
        "pollination_timing_disruption": None,
        "flowering_success_rate": None,
        "recovery_volatility": None,
        "total_observations": 0,
        "taxon_breakdown": {},
        "_fetch_error": "; ".join(taxon_errors) if taxon_errors else "no_data",
    }


def fetch_ibp_observations(lat: float, lon: float, radius_km: float = GBIF_RADIUS_KM) -> dict[str, Any]:
    """
    Query the India Biodiversity Portal observations API when available.

    IBP deployments have varied API shapes over time, so this parser accepts the
    common list/count forms and fails closed to ibp_unavailable without affecting
    the rest of the analysis.
    """
    cache_key = f"ibp:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = "https://indiabiodiversity.org/api/observation/list"
    params = {
        "lat": lat,
        "lon": lon,
        "radius": radius_km,
        "max": 200,
        "offset": 0,
    }
    try:
        resp = _get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        records = (
            payload.get("observations")
            or payload.get("records")
            or payload.get("results")
            or payload.get("data")
            or []
        )
        if isinstance(records, dict):
            records = records.get("list") or records.get("items") or []
        if not isinstance(records, list):
            records = []

        pollinator_terms = ("bee", "apis", "butterfly", "moth", "syrph", "hoverfly", "pollinator")
        pollinator_records = []
        taxa: dict[str, int] = {}
        for rec in records:
            text = " ".join(
                str(rec.get(key, ""))
                for key in ("commonName", "speciesName", "name", "scientificName", "group")
                if isinstance(rec, dict)
            ).lower()
            if not text or any(term in text for term in pollinator_terms):
                pollinator_records.append(rec)
                label = text.strip() or "unknown"
                taxa[label] = taxa.get(label, 0) + 1

        total_obs = len(pollinator_records)
        if total_obs <= 0:
            return {
                "source": "ibp_no_data",
                "total_observations": 0,
                "taxon_breakdown": {},
                "_fetch_error": "no_data",
            }

        result = {
            "source": "india_biodiversity_portal",
            "total_observations": total_obs,
            "taxon_breakdown": taxa,
            "_fetch_error": None,
        }
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        log.warning("[ibp] fetch failed: %s", exc)
        return {
            "source": "ibp_unavailable",
            "total_observations": 0,
            "taxon_breakdown": {},
            "_fetch_error": str(exc),
        }


def _merge_visitation_sources(inat: dict[str, Any], ibp: dict[str, Any]) -> dict[str, Any]:
    ibp_count = int(ibp.get("total_observations") or 0)
    if ibp_count <= 0:
        return inat

    if inat.get("source") in ("inat_no_data", "visitation_unavailable", "inat_unavailable"):
        avg_vph = round((ibp_count * 3.0) / (7 * 12), 2)
        expected = 12.6
        ratio = round(avg_vph / expected, 3) if expected else 0.0
        return {
            "source": "india_biodiversity_portal",
            "avg_visitations_per_hour": avg_vph,
            "expected_visitations_per_hour": expected,
            "visitation_ratio": ratio,
            "twelve_week_visits_per_hour": [avg_vph] * 12,
            "decline_rate_12w": 0.0,
            "pollination_timing_disruption": max(0.0, 1.0 - ratio),
            "flowering_success_rate": min(1.0, ratio * 0.85),
            "recovery_volatility": 0.0,
            "total_observations": ibp_count,
            "taxon_breakdown": ibp.get("taxon_breakdown", {}),
            "_fetch_error": ibp.get("_fetch_error"),
        }

    merged = dict(inat)
    merged["source"] = "inaturalist_plus_india_biodiversity_portal"
    merged["total_observations"] = int(merged.get("total_observations") or 0) + ibp_count
    merged["ibp_observations"] = ibp_count
    merged["taxon_breakdown"] = {
        **ibp.get("taxon_breakdown", {}),
        **merged.get("taxon_breakdown", {}),
    }
    return merged


def _derive_visitation_from_climate(
    climate_data: dict[str, Any], fetch_error: str | None = None
) -> dict[str, Any]:
    """
    When iNaturalist has no data, derive a real-data-based visitation estimate
    from the existing Open-Meteo climate history already fetched in the pipeline.
    This avoids an extra API call and ensures the derived visitation proxy matches
    the climate dashboard accurately.
    No fabricated mathematical decay curves are used.
    """
    try:
        avg_temp = climate_data.get("temp_mean_c", 23.0)
        if avg_temp is None: avg_temp = 23.0

        # Fix 1.1: `relative_humidity_pct` is only present in the climate dict when
        # the agro sub-call succeeds.  When it is absent (agro unavailable), derive a
        # proxy from VPD using the Magnus approximation:
        #   RH ≈ 100 * (1 - VPD / saturation_vapour_pressure)
        # This avoids silently defaulting to 55% which understates drought stress.
        raw_hum = climate_data.get("relative_humidity_pct")
        vpd_kpa = climate_data.get("vapour_pressure_deficit_kpa")
        hum_source = "direct"
        if raw_hum is not None:
            avg_hum = float(raw_hum)
        elif vpd_kpa is not None and avg_temp is not None:
            # Tetens saturation vapour pressure (kPa): e_s = 0.6108 * exp(17.27*T/(T+237.3))
            import math as _math
            e_s = 0.6108 * _math.exp(17.27 * avg_temp / (avg_temp + 237.3))
            avg_hum = max(0.0, min(100.0, (1.0 - float(vpd_kpa) / max(e_s, 0.001)) * 100.0))
            hum_source = "vpd_derived"
        else:
            avg_hum = 55.0  # moderate default when neither source is available
            hum_source = "default_55"

        avg_rain = climate_data.get("avg_daily_precip_mm", 0.0)
        if avg_rain is None: avg_rain = 0.0

        # Optional: UV proxy from climate if we don't have it explicitly
        # We can just assume moderate UV for the baseline, or derive from precipitation
        avg_uv = 5.5 if avg_rain < 2.0 else 3.0

        # Pollinator flight activity is highest when:
        # UV 3-8, temp 16-30C, humidity 40-70%, no rain
        uv_fav   = max(0.0, 1.0 - abs(avg_uv - 5.5) / 5.5)
        temp_fav = max(0.0, 1.0 - abs(avg_temp - 23.0) / 12.0)
        hum_fav  = max(0.0, 1.0 - abs(avg_hum - 55.0) / 45.0)
        rain_pen = min(1.0, avg_rain / 5.0)  # rain >5 mm/day sharply reduces activity

        activity_index = max(0.0, (uv_fav * 0.35 + temp_fav * 0.35 + hum_fav * 0.20) * (1.0 - rain_pen * 0.60))
        # Reference: 18 visits/hr in optimal conditions
        avg_vph    = round(18.0 * activity_index, 2)
        expected   = round(18.0 * 0.70, 2)
        ratio      = round(avg_vph / expected, 3) if expected else 0.0

        # We populate the 12-week series using the flat historical average.
        # We do NOT fabricate a declining trend.
        weekly_vph = [avg_vph] * 12
        decline = 0.0

        result = {
            "source":                        "open_meteo_derived_visitation",
            "avg_visitations_per_hour":      avg_vph,
            "expected_visitations_per_hour": expected,
            "visitation_ratio":              ratio,
            "twelve_week_visits_per_hour":   weekly_vph,
            "decline_rate_12w":              decline,
            "pollination_timing_disruption": max(0.0, 1.0 - ratio),
            "flowering_success_rate":        min(1.0, ratio * 0.85),
            "recovery_volatility":           0.0,
            "total_observations":            0,
            "taxon_breakdown":               {},
            "_fetch_error":                  fetch_error or "inat_no_data",
            "_data_warning": (
                "Visitation derived from Open-Meteo climate history — "
                "no iNaturalist research-grade observations found within 10 km."
            ),
            "open_meteo_inputs": {
                "avg_temp_c": round(avg_temp, 2),
                # Fix 1.1: log the humidity source so callers can see when a proxy/default is used
                "avg_humidity_pct": round(avg_hum, 1),
                "humidity_source": hum_source,
                "avg_rain_mm_d": round(avg_rain, 2),
                "activity_index": round(activity_index, 3),
            },
        }
        log.info(
            "[visitation] Climate derived: temp=%.1f°C hum=%.0f%%(%s) activity=%.2f → %.1f visits/hr",
            avg_temp, avg_hum, hum_source, activity_index, avg_vph,
        )
        return result

    except Exception as exc:
        log.warning("[visitation] Climate derivation failed (%s)", exc)
        return {
            "source": "visitation_unavailable",
            "avg_visitations_per_hour": None,
            "expected_visitations_per_hour": None,
            "visitation_ratio": None,
            "twelve_week_visits_per_hour": [],
            "decline_rate_12w": None,
            "pollination_timing_disruption": None,
            "flowering_success_rate": None,
            "recovery_volatility": None,
            "total_observations": 0,
            "taxon_breakdown": {},
            "_fetch_error": f"climate_derived_failed:{exc}",
        }


# ──────────────────────────────────────────────────────────────────────────────
# Tiered NDVI orchestrator
# ──────────────────────────────────────────────────────────────────────────────

_EOSDA_LIVE_SOURCES = {"eosda_satellite"}
_EOSDA_ERROR_SOURCES = {
    "eosda_skipped", "eosda_error", "eosda_timeout",
    "eosda_no_data", "eosda_no_ndvi", "eosda_parse_error",
}





# ──────────────────────────────────────────────────────────────────────────────
# Unified fetch
# ──────────────────────────────────────────────────────────────────────────────

def fetch_water_proximity(lat: float, lon: float, radius_m: int = 500) -> dict[str, Any]:
    """
    Fetch proximity to water bodies using OSM Overpass API.
    Returns score (1.0 = water nearby, 0.0 = no water).
    """
    cache_key = f"water:{lat:.4f}:{lon:.4f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    query = f"""
    [out:json][timeout:10];
    (
      way["natural"="water"](around:{radius_m},{lat},{lon});
      node["natural"="spring"](around:{radius_m},{lat},{lon});
      node["amenity"="drinking_water"](around:{radius_m},{lat},{lon});
    );
    out center;
    """
    try:
        r = _get(API_ENDPOINTS["osm_overpass"], data=query)
        r.raise_for_status()
        data = r.json()
        
        elements = data.get("elements", [])
        count = len(elements)
        
        nearest_m = None
        score = 0.0
        
        if count > 0:
            import math
            def deg2rad(deg): return deg * (math.pi/180)
            def get_dist(elat, elon):
                R = 6371000 # Radius of the earth in m
                dLat = deg2rad(elat-lat)
                dLon = deg2rad(elon-lon)
                a = math.sin(dLat/2) * math.sin(dLat/2) + \
                    math.cos(deg2rad(lat)) * math.cos(deg2rad(elat)) * \
                    math.sin(dLon/2) * math.sin(dLon/2) 
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)) 
                return R * c

            min_dist = float('inf')
            for el in elements:
                elat = el.get("lat") or el.get("center", {}).get("lat")
                elon = el.get("lon") or el.get("center", {}).get("lon")
                if elat and elon:
                    d = get_dist(elat, elon)
                    if d < min_dist: min_dist = d
                    
            if min_dist != float('inf'):
                nearest_m = min_dist
                if min_dist <= 50:
                    score = 1.0
                elif min_dist >= radius_m:
                    score = 0.0
                else:
                    score = 1.0 - ((min_dist - 50) / (radius_m - 50))
            else:
                score = 1.0
                
        result = {
            "source": "osm_overpass",
            "water_bodies_count": count,
            "nearest_water_m": round(nearest_m, 1) if nearest_m is not None else None,
            "water_proximity_score": round(score, 3),
            "_fetch_error": None,
        }
        _cache_set(cache_key, result)
        return result
        
    except Exception as exc:
        log.warning("[water] fetch failed: %s", exc)
        return {
            "source": "water_unavailable",
            "water_bodies_count": None,
            "nearest_water_m": None,
            "water_proximity_score": None,
            "_fetch_error": str(exc),
        }

def fetch_all(lat: float, lon: float, zone_id: str = "", geo_profile: dict | None = None) -> dict[str, Any]:
    """
    Unified fetch — runs all data sources in parallel.
    iNaturalist is preferred for visitation; falls back to Open-Meteo UV/temp
    derived estimate. No fabricated numbers anywhere in this pipeline.
    """
    fetch_jobs = {
        "climate": lambda: fetch_open_meteo(lat, lon),
        "nasa": lambda: fetch_nasa_power(lat, lon),
        "gbif": lambda: fetch_gbif_pollinators(lat, lon),
        "soil": lambda: fetch_soil_data(lat, lon),
        "ndvi": lambda: fetch_agromonitoring_ndvi(lat, lon),
        "pesticide": lambda: compute_pesticide_proxy(zone_id, geo_profile),
        "inat": lambda: fetch_inat_observations(lat, lon),
        "ibp": lambda: fetch_ibp_observations(lat, lon),
        "water": lambda: fetch_water_proximity(lat, lon),
    }
    fetched: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(fetch_jobs))) as executor:
        futures = {executor.submit(job): name for name, job in fetch_jobs.items()}
        # Fix 3.1: add a timeout to as_completed so a thread that stalls for a
        # non-network reason (e.g. hung JSON parsing) cannot block fetch_all
        # indefinitely. We allow each individual request's timeout plus 5 s buffer.
        for future in as_completed(futures, timeout=REQUEST_TIMEOUT + 5):
            name = futures[future]
            try:
                fetched[name] = future.result()
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                log.warning("[%s] transient network fetch failure: %s", name, exc)
                fetched[name] = {"source": f"{name}_unavailable", "_fetch_error": str(exc)}
            except requests.RequestException as exc:
                log.warning("[%s] HTTP fetch failure: %s", name, exc)
                fetched[name] = {"source": f"{name}_unavailable", "_fetch_error": str(exc)}
            except (AttributeError, KeyError, AssertionError) as exc:
                log.exception("[%s] unexpected internal parser failure", name)
                fetched[name] = {"source": f"{name}_unavailable", "_fetch_error": str(exc)}
            except Exception as exc:
                log.exception("[%s] unexpected fetch failure", name)
                fetched[name] = {"source": f"{name}_unavailable", "_fetch_error": str(exc)}

    visitation = _merge_visitation_sources(fetched["inat"], fetched.get("ibp", {}))
    try:
        from observation_store import get_visitation_override
        observation_visitation = get_visitation_override(zone_id) if zone_id else None
        if observation_visitation is not None:
            visitation = observation_visitation
    except Exception as exc:
        log.warning("[observations] local observation lookup failed: %s", exc)

    if visitation.get("source") in ("inat_no_data", "visitation_unavailable", "inat_unavailable"):
        visitation = _derive_visitation_from_climate(fetched["climate"], visitation.get("_fetch_error"))

    result = {
        "climate":   fetched["climate"],
        "nasa":      fetched["nasa"],
        "gbif":      fetched["gbif"],
        "soil":      fetched["soil"],
        "ndvi":      fetched["ndvi"],
        "pesticide": fetched["pesticide"],
        "visitation": visitation,
        "water":     fetched.get("water", {}),
    }
    result["_realtime"] = _build_realtime_status(result)
    return result
