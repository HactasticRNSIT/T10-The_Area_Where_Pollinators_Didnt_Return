import os
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# External API endpoints
# ──────────────────────────────────────────────────────────────────────────────
API_ENDPOINTS = {
    # Open-Meteo historical climate data (no API key)
    "open_meteo": "https://archive-api.open-meteo.com/v1/archive",

    # NASA POWER daily data (no API key)
    "nasa_power": "https://power.larc.nasa.gov/api/temporal/daily/point",

    # GBIF species occurrence search (no API key)
    "gbif_occurrences": "https://api.gbif.org/v1/occurrence/search",

    # ISRIC SoilGrids REST API (primary soil data source, currently intermittent)
    "soilgrids": "https://rest.isric.org/soilgrids/v2.0/properties/query",

    # OpenLandMap STAC catalog (alternative soil source via OpenLandMap/OpenGeoHub)
    "openlandmap_stac": "https://s3.eu-central-1.wasabisys.com/stac/openlandmap/catalog.json",

    # Groq LLM inference
    "groq": "https://api.groq.com/openai/v1/chat/completions",

    # Agromonitoring (Sentinel-2 / Landsat-8 NDVI via OpenWeather)
    "agromonitoring_polygons":     "http://api.agromonitoring.com/agro/1.0/polygons",
    "agromonitoring_image_search": "http://api.agromonitoring.com/agro/1.0/image/search",
    "agromonitoring_ndvi_history": "http://api.agromonitoring.com/agro/1.0/ndvi/history",
}

# ──────────────────────────────────────────────────────────────────────────────
# Factor weights (must sum to 1.0)
# ──────────────────────────────────────────────────────────────────────────────
FACTOR_WEIGHTS = {
    "pesticide_exposure":  0.32,
    "soil_fertility":      0.23,
    "floral_diversity":    0.17,
    "climate_variability": 0.12,
    "nesting_availability": 0.08,
    "pollination_factor":  0.08,
}

# ──────────────────────────────────────────────────────────────────────────────
# Activity score classification thresholds
# Score = (1 - weighted_stress) * 100   (higher = healthier)
# ──────────────────────────────────────────────────────────────────────────────
ACTIVITY_SCORE_LABELS = [
    (80, 100, "Healthy"),
    (60,  80, "Moderate"),
    (40,  60, "Stressed"),
    (20,  40, "Critical"),
    (  0,  20, "Collapse Risk"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Pollination stress index thresholds (based on overall stress score 0-1)
# ──────────────────────────────────────────────────────────────────────────────
STRESS_INDEX_THRESHOLDS = [
    (0.00, 0.25, "Low"),
    (0.25, 0.50, "Medium"),
    (0.50, 0.75, "High"),
    (0.75, 1.00, "Severe"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Anomaly detection thresholds (rule-based, Layer 1)
# ──────────────────────────────────────────────────────────────────────────────
ANOMALY_THRESHOLDS = {
    # Pesticide
    "pesticide_ppm_warning":       5.0,    # ppm
    "pesticide_ppm_critical":      15.0,
    "pesticide_freq_warning":      3,      # applications per month
    "pesticide_freq_critical":     6,

    # Soil
    "ph_low_warning":              5.5,
    "ph_high_warning":             7.5,
    "ph_critical_low":             5.0,
    "ph_critical_high":            8.0,
    "organic_carbon_low_warning":  1.5,    # g/kg
    "organic_carbon_critical":     0.8,
    "nitrogen_low_warning":        1.0,    # g/kg
    "nitrogen_critical":           0.5,

    # Climate (30-day window)
    "temp_variance_warning":       8.0,    # °C standard deviation
    "temp_variance_critical":      14.0,
    "rainfall_deficit_warning":    30.0,   # mm below 30-day average
    "rainfall_deficit_critical":   60.0,
    "drought_index_warning":       0.4,    # 0–1
    "drought_index_critical":      0.7,

    # Floral / NDVI
    "ndvi_low_warning":            0.35,
    "ndvi_low_critical":           0.20,
    "species_count_warning":       5,      # unique pollinator species
    "species_count_critical":      2,
    "visitation_ratio_warning":    0.65,   # observed / expected visits per hour
    "visitation_ratio_critical":   0.40,
    "visitation_decline_warning":  0.25,   # 12-week decline fraction
    "visitation_decline_critical": 0.45,
    "timing_disruption_warning":   0.45,
    "timing_disruption_critical":  0.70,
    "flowering_success_warning":   0.55,
    "flowering_success_critical":  0.35,

    # Nesting
    "bare_soil_warning":           0.30,   # fraction 0–1
    "bare_soil_critical":          0.55,
    "disturbance_warning":         0.50,
    "disturbance_critical":        0.75,
}

# ──────────────────────────────────────────────────────────────────────────────
# Geographic crop registry
# Maps zone_id prefix → {crop: pollinator_dependency (0–1)}
# dependency = fraction of that crop's yield relying on pollinators
#
# Lookup: get_crop_dependency_for_zone(zone_id) tries longest-prefix match,
# then falls back to DEFAULT_CROP_POLLINATION_DEPENDENCY.
# ──────────────────────────────────────────────────────────────────────────────

# Default (Europe / generic)
DEFAULT_CROP_POLLINATION_DEPENDENCY = {
    "almonds":     1.00,
    "blueberries": 0.90,
    "canola":      0.70,
    "sunflower":   0.65,
    "wheat":       0.10,
    "maize":       0.05,
}

ZONE_CROP_REGISTRY: dict[str, dict[str, float]] = {
    # --- Major States (Existing + New) ---
    "IN_KA": {"sunflower": 0.90, "cotton": 0.15, "red gram": 0.40, "groundnut": 0.30, "coffee": 0.55},
    "IN_RJ": {"mustard": 0.80, "cumin": 0.65, "coriander": 0.60, "wheat": 0.10, "bajra": 0.35},
    "IN_UP": {"mango": 0.75, "sugarcane": 0.02, "wheat": 0.10, "potato": 0.10, "barley": 0.05},
    "IN_GJ": {"cotton": 0.15, "groundnut": 0.30, "castor": 0.35, "wheat": 0.10, "bajra": 0.35},
    "IN_WB": {"rice": 0.03, "jute": 0.05, "mustard": 0.80, "tea": 0.70, "potato": 0.10},
    "IN_KL": {"cardamom": 0.95, "black pepper": 0.60, "coffee": 0.55, "coconut": 0.30, "rubber": 0.05},
    "IN_HP": {"apple": 0.95, "cherry": 0.90, "plum": 0.70, "wheat": 0.10, "potato": 0.10},
    "IN_MH": {"orange": 0.75, "cotton": 0.15, "soybean": 0.25, "pomegranate": 0.60, "tur": 0.30},
    "IN_MP": {"soybean": 0.25, "wheat": 0.10, "gram": 0.20, "garlic": 0.40, "coriander": 0.60},
    "IN_BR": {"lychee": 0.80, "mango": 0.75, "maize": 0.05, "wheat": 0.10, "sugarcane": 0.02},
    "IN_TN": {"coconut": 0.30, "rice": 0.03, "cotton": 0.15, "groundnut": 0.30, "bananas": 0.10},
    "IN_AP": {"chillies": 0.60, "tobacco": 0.05, "cotton": 0.15, "rice": 0.03, "groundnut": 0.30},
    "IN_TG": {"turmeric": 0.50, "cotton": 0.15, "maize": 0.05, "chillies": 0.60, "rice": 0.03},
    "IN_PB": {"wheat": 0.10, "rice": 0.03, "cotton": 0.15, "mustard": 0.80, "sugarcane": 0.02},
    "IN_HR": {"mustard": 0.80, "wheat": 0.10, "rice": 0.03, "cotton": 0.15, "sugarcane": 0.02},
    "IN_AS": {"tea": 0.70, "rice": 0.03, "jute": 0.05, "citrus": 0.50},
    "IN_OR": {"rice": 0.03, "jute": 0.05, "groundnut": 0.30, "pulses": 0.40},
    "IN_CT": {"rice": 0.03, "maize": 0.05, "pulses": 0.40, "oilseeds": 0.40},
    "IN_JH": {"rice": 0.03, "maize": 0.05, "pulses": 0.40, "ragi": 0.20},
    "IN_UT": {"wheat": 0.10, "rice": 0.03, "millets": 0.20, "fruits": 0.60},
    "IN_GA": {"cashew": 0.70, "coconut": 0.30, "rice": 0.03},
    "IN_SK": {"cardamom": 0.95, "ginger": 0.50, "orange": 0.75, "maize": 0.05},
    "IN_JK": {"apple": 0.95, "saffron": 0.90, "walnut": 0.85, "almond": 1.00},
    "IN_LA": {"apricot": 0.85, "barley": 0.05, "vegetables": 0.45},
    "IN_TR": {"rubber": 0.05, "tea": 0.70, "pineapple": 0.80, "rice": 0.03},
    "IN_ML": {"pineapple": 0.80, "orange": 0.75, "ginger": 0.50, "turmeric": 0.50},
    "IN_MN": {"pineapple": 0.80, "orange": 0.75, "rice": 0.03, "maize": 0.05},
    "IN_MZ": {"ginger": 0.50, "turmeric": 0.50, "pineapple": 0.80, "rice": 0.03},
    "IN_NL": {"maize": 0.05, "rice": 0.03, "pulses": 0.40, "citrus": 0.50},
    "IN_AR": {"orange": 0.75, "pineapple": 0.80, "kiwi": 0.90, "maize": 0.05},
    "IN_DL": {"wheat": 0.10, "vegetables": 0.45, "mustard": 0.80},
    "IN_CH": {"wheat": 0.10, "rice": 0.03},
    "IN_PY": {"rice": 0.03, "coconut": 0.30, "groundnut": 0.30},
    "IN_AN": {"coconut": 0.30, "areca nut": 0.40, "rice": 0.03},
    "IN_LD": {"coconut": 0.30, "tapioca": 0.10},
    "IN_DN": {"rice": 0.03, "jowar": 0.05, "pulses": 0.40},

    # --- International / Generic ---
    "FARM_G": {"almonds": 1.00, "stone fruit": 0.85, "tomatoes": 0.55, "grapes": 0.10, "canola": 0.70},
    "FARM_H": {"maize": 0.05, "soybean": 0.25, "sunflower": 0.65, "canola": 0.70, "wheat": 0.10},
}


def get_crop_dependency_for_zone(zone_id: str) -> dict[str, float]:
    """
    Return the crop–dependency dict for a given zone_id.

    Matching strategy (longest prefix wins):
      zone_id = "IN_GJ_01"  → tries "IN_GJ_01", then "IN_GJ", then "IN"
    Falls back to DEFAULT_CROP_POLLINATION_DEPENDENCY for unknown zones.
    """
    if not zone_id:
        return DEFAULT_CROP_POLLINATION_DEPENDENCY
    # Try progressively shorter prefixes
    parts = zone_id.split("_")
    for length in range(len(parts), 0, -1):
        prefix = "_".join(parts[:length])
        if prefix in ZONE_CROP_REGISTRY:
            return ZONE_CROP_REGISTRY[prefix]
    return DEFAULT_CROP_POLLINATION_DEPENDENCY

# ──────────────────────────────────────────────────────────────────────────────
# Crop risk label bands (stress_impact = dependency * overall_stress)
# ──────────────────────────────────────────────────────────────────────────────
CROP_RISK_LABELS = [
    (0.00, 0.20, "Low"),
    (0.20, 0.45, "Moderate"),
    (0.45, 0.70, "High"),
    (0.70, 1.00, "Severe"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Open-Meteo variables to request
# ──────────────────────────────────────────────────────────────────────────────
OPEN_METEO_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_speed_10m_max",
    "et0_fao_evapotranspiration",
]

# ──────────────────────────────────────────────────────────────────────────────
# NASA POWER variables to request
# ──────────────────────────────────────────────────────────────────────────────
NASA_POWER_VARS = [
    "GWETROOT",    # root-zone soil wetness (0–1)
    "GWETPROF",    # profile soil wetness
    "T2M",         # temperature at 2 m
    "PRECTOTCORR", # precipitation corrected
]

# ──────────────────────────────────────────────────────────────────────────────
# GBIF pollinator taxon keys (bees, butterflies, hoverflies)
# ──────────────────────────────────────────────────────────────────────────────
GBIF_POLLINATOR_TAXON_KEYS = [
    1340278,  # Apidae (bees)
    5473,     # Lepidoptera (butterflies & moths)
    6920,     # Syrphidae (hoverflies)
    1340,     # Hymenoptera (broader)
]

# ──────────────────────────────────────────────────────────────────────────────
# Data look-back windows
# ──────────────────────────────────────────────────────────────────────────────
CLIMATE_LOOKBACK_DAYS = 30
GBIF_RADIUS_KM = 10          # search radius around zone coordinates
GBIF_MAX_RECORDS = 300

# ──────────────────────────────────────────────────────────────────────────────
# AI layer config (Groq)
# ──────────────────────────────────────────────────────────────────────────────
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_MAX_TOKENS = 1024
GROQ_TEMPERATURE = 0.3
AI_CALL_MIN_SEVERITY = "WARNING"  # trigger AI for WARNING or CRITICAL

# ──────────────────────────────────────────────────────────────────────────────
# Habitat suitability scoring weights (sub-component of nesting)
# ──────────────────────────────────────────────────────────────────────────────
HABITAT_WEIGHTS = {
    "floral_diversity": 0.40,
    "nesting_availability": 0.35,
    "soil_fertility": 0.25,
}

# ──────────────────────────────────────────────────────────────────────────────
# Request timeouts (seconds)
# ──────────────────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 15

# ──────────────────────────────────────────────────────────────────────────────
# Agromonitoring credentials + geometry
# ──────────────────────────────────────────────────────────────────────────────
AGROMONITORING_API_KEY: str = os.environ.get("AGROMONITORING_API_KEY", "")
# Half-side of the square polygon created around a lat/lon point.
# 0.0045 deg ~ 0.5 km gives a ~1 km2 field polygon (minimum for meaningful NDVI).
AGROMONITORING_POLYGON_HALF_DEG: float = 0.0045
# Look-back window for image search (days).
AGROMONITORING_IMAGE_WINDOW_DAYS: int = 30
# Maximum cloud coverage accepted when selecting a satellite image.
AGROMONITORING_MAX_CLOUD_PCT: float = 30.0

# ──────────────────────────────────────────────────────────────────────────────
# Fix 6: Per-zone YAML weight overrides
# Loaded once at import time from zone_weights.yaml (sibling of config.py).
# Falls back to FACTOR_WEIGHTS if the file is absent or unparseable.
# ──────────────────────────────────────────────────────────────────────────────

import os as _os
import pathlib as _pathlib

_ZONE_WEIGHTS_PATH = _pathlib.Path(__file__).parent / "zone_weights.yaml"
_ZONE_WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {}


def _load_zone_weights() -> None:
    """Parse zone_weights.yaml into _ZONE_WEIGHT_OVERRIDES (longest-prefix lookup)."""
    global _ZONE_WEIGHT_OVERRIDES
    if not _ZONE_WEIGHTS_PATH.exists():
        return
    try:
        import yaml  # PyYAML optional dependency
        with open(_ZONE_WEIGHTS_PATH) as fh:
            data = yaml.safe_load(fh) or {}
        validated: dict[str, dict[str, float]] = {}
        expected_keys = set(FACTOR_WEIGHTS.keys())
        for zone_prefix, weights in data.items():
            if not isinstance(weights, dict):
                continue
            if set(weights.keys()) != expected_keys:
                continue
            total = sum(weights.values())
            if abs(total - 1.0) > 0.01:
                continue  # skip malformed entries silently
            validated[zone_prefix] = {k: float(v) for k, v in weights.items()}
        _ZONE_WEIGHT_OVERRIDES = validated
    except Exception:
        _ZONE_WEIGHT_OVERRIDES = {}


_load_zone_weights()


def get_factor_weights_for_zone(zone_id: str) -> dict[str, float]:
    """
    Return the factor weights for a given zone_id.
    Longest-prefix match against zone_weights.yaml; falls back to global
    FACTOR_WEIGHTS if no override exists.

    Example:
        zone_id = "IN_KA_01" → tries "IN_KA_01", "IN_KA", "IN" → first match wins.
    """
    if not zone_id:
        return FACTOR_WEIGHTS
    parts = zone_id.split("_")
    for length in range(len(parts), 0, -1):
        prefix = "_".join(parts[:length])
        if prefix in _ZONE_WEIGHT_OVERRIDES:
            return _ZONE_WEIGHT_OVERRIDES[prefix]
    return FACTOR_WEIGHTS

# ──────────────────────────────────────────────────────────────────────────────
# Fix 8: Agro-climatic zone threshold overrides
# Allows anomaly detection to use geography-aware thresholds instead of
# a single global table, eliminating false positives in tropical/arid zones.
# ──────────────────────────────────────────────────────────────────────────────

# Base thresholds remain ANOMALY_THRESHOLDS (imported from above).
# Zone overrides are shallow-merged on top; unspecified keys use the global value.

_AGRO_ZONE_THRESHOLD_OVERRIDES: dict[str, dict[str, Any]] = {
    # Indian tropical / sub-tropical zones: raise temp variance thresholds
    # (diurnal swings of 10–15 °C are climatically normal here)
    "IN": {
        "temp_variance_warning":  12.0,   # was 8.0
        "temp_variance_critical": 20.0,   # was 14.0
        # Monsoon zones routinely exceed 30 mm/30 days; lower rainfall threshold
        "rainfall_deficit_warning":  10.0,  # was 30.0
        "rainfall_deficit_critical": 25.0,  # was 60.0
        # Drought index baseline is higher in arid Indian zones
        "drought_index_warning":  0.55,    # was 0.40
        "drought_index_critical": 0.80,    # was 0.70
    },
    # Rajasthan / Gujarat: hyper-arid; further relax rainfall deficit thresholds
    "IN_RJ": {
        "temp_variance_warning":     14.0,
        "temp_variance_critical":    22.0,
        "rainfall_deficit_warning":   5.0,
        "rainfall_deficit_critical": 15.0,
        "drought_index_warning":      0.65,
        "drought_index_critical":     0.88,
    },
    "IN_GJ": {
        "rainfall_deficit_warning":   8.0,
        "rainfall_deficit_critical": 18.0,
        "drought_index_warning":      0.60,
        "drought_index_critical":     0.85,
    },
    # Kerala spice coast: high humidity; NDVI thresholds raised (dense canopy)
    "IN_KL": {
        "ndvi_low_warning":  0.45,    # was 0.35 — tropical canopy baseline is higher
        "ndvi_low_critical": 0.30,    # was 0.20
    },
    # Himachal Pradesh: temperate; keep standard thresholds (European defaults fine)
}


def get_anomaly_thresholds_for_zone(zone_id: str) -> dict[str, Any]:
    """
    Return anomaly detection thresholds for a zone, merging global defaults
    with any agro-climatic zone overrides (longest-prefix match).

    Example:
        zone_id = "IN_RJ_01" → merges "IN" overrides, then "IN_RJ" overrides on top.
    """
    merged = dict(ANOMALY_THRESHOLDS)  # start from global defaults
    if not zone_id:
        return merged

    parts = zone_id.split("_")
    # Apply overrides from shortest prefix to longest so specific zones win
    for length in range(1, len(parts) + 1):
        prefix = "_".join(parts[:length])
        if prefix in _AGRO_ZONE_THRESHOLD_OVERRIDES:
            merged.update(_AGRO_ZONE_THRESHOLD_OVERRIDES[prefix])

    return merged
