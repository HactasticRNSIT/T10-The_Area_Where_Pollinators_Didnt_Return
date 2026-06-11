import os
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# External API endpoints
# ──────────────────────────────────────────────────────────────────────────────
API_ENDPOINTS = {
    # Open-Meteo historical climate data (no API key)
    "open_meteo": "https://archive-api.open-meteo.com/v1/archive",
    "open_meteo_forecast": "https://api.open-meteo.com/v1/forecast",

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
    # Fix 2.4: upgraded to https:// so the appid API key is never sent in cleartext.
    "agromonitoring_polygons":     "https://api.agromonitoring.com/agro/1.0/polygons",
    "agromonitoring_image_search": "https://api.agromonitoring.com/agro/1.0/image/search",
    "agromonitoring_ndvi_history": "https://api.agromonitoring.com/agro/1.0/ndvi/history",


    # OpenStreetMap Nominatim — free reverse geocoding, no API key required.
    # Usage policy: max 1 req/s; descriptive User-Agent must be set.
    "nominatim_reverse": "https://nominatim.openstreetmap.org/reverse",

    # OSM Overpass API for proximity queries
    "osm_overpass": "https://overpass-api.de/api/interpreter",
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

    # Wind speed (km/h) — bee foraging is disrupted above 15 km/h and ceases
    # entirely above 25 km/h (COLOSS BeeBook field protocols; IBRA field guide).
    "wind_speed_warning":          15.0,
    "wind_speed_critical":         25.0,
}

# ──────────────────────────────────────────────────────────────────────────────
# Geographic crop registry
# Maps zone_id prefix → {crop: pollinator_dependency (0–1)}
# dependency = fraction of that crop's yield relying on pollinators
#
# Lookup: get_crop_dependency_for_zone(zone_id) tries longest-prefix match,
# then falls back to DEFAULT_CROP_POLLINATION_DEPENDENCY.
# ──────────────────────────────────────────────────────────────────────────────

# India-oriented fallback used when no dynamic geo_profile is available.
# The platform is focused on Indian agriculture, so avoid European defaults
# such as almonds/blueberries unless a regional classifier explicitly returns them.
DEFAULT_CROP_POLLINATION_DEPENDENCY = {
    "mustard":   0.80,
    "sunflower": 0.65,
    "mango":     0.75,
    "cotton":    0.15,
    "rice":      0.03,
    "wheat":     0.10,
}

ZONE_DEFAULT_CROP_MAPPINGS = {
    "IN_KA": {"sunflower": 0.65},
    "IN_RJ": {"mustard": 0.80},
    "IN_UP": {"mango": 0.75},
    "IN_GJ": {"cotton": 0.15},
    "IN_WB": {"rice": 0.03},
    "IN_KL": {"cardamom": 0.60},
    "IN_HP": {"apple": 0.95},
    "IN_MH": {"orange": 0.60},
    "IN_MP": {"sesame": 0.65},
    "IN_BR": {"lychee": 0.75},
    "IN_TN": {"coconut": 0.30},
    "IN_PB": {"wheat": 0.10},
    "IN_AS": {"tea": 0.70},
    "IN_TG": {"turmeric": 0.50},
    "IN_JK": {"saffron": 0.80},
}

def get_crop_dependency_for_zone(zone_id: str, geo_profile: dict = None) -> dict[str, float]:
    """
    Return the crop-dependency dict for a given zone_id.
    Relies on the dynamically resolved geo_profile (state registry -> LLM -> climate fallback).
    """
    if geo_profile and 'crops' in geo_profile:
        return geo_profile['crops']

    if zone_id:
        parts = zone_id.split("_")
        for length in range(len(parts), 0, -1):
            prefix = "_".join(parts[:length])
            if prefix in ZONE_DEFAULT_CROP_MAPPINGS:
                return ZONE_DEFAULT_CROP_MAPPINGS[prefix]

    return DEFAULT_CROP_POLLINATION_DEPENDENCY

# ──────────────────────────────────────────────────────────────────────────────
# Species count normalisation constants
# ──────────────────────────────────────────────────────────────────────────────
# RESILIENCE_MAX_SPECIES_COUNT: species_count at which biodiversity axis of the
#   resilience score saturates at 1.0.  Calibrated from pan-European farmland
#   pollinator surveys (Woodcock et al. 2016) which report 12–18 morphospecies
#   in a 10 km radius as a healthy baseline.  Tropical high-biodiversity zones
#   (e.g. Kerala) should set this higher via zone override.
# FLORAL_MAX_SPECIES_COUNT: species_count at which the floral diversity factor
#   stress component reaches 0 (no stress).  12 is the median for Indo-Gangetic
#   plain agricultural landscapes (GBIF India occurrence data, 2020-2024).
#   Override for Western Ghats / Andaman zones where 20+ species are baseline.
# Fix 4.2: Legacy aliases removed. Use SPECIES_COUNT_RESILIENCE_NORM and
# SPECIES_COUNT_FLORAL_NORM directly in all code. Aliases were identical copies
# that could silently diverge if only one constant was updated in future.
SPECIES_COUNT_RESILIENCE_NORM: float = 15.0
SPECIES_COUNT_FLORAL_NORM: float = 12.0

# Per-zone species-norm overrides.  Any zone prefix listed here replaces the
# global constant.  Follows the same longest-prefix lookup as factor weights.
_ZONE_SPECIES_NORM_OVERRIDES: dict[str, dict[str, float]] = {
    # Kerala / Western Ghats: one of the world's biodiversity hotspots.
    # 20+ pollinator morphospecies are a normal baseline in spice-coast agroforestry.
    "IN_KL": {"resilience": 22.0, "floral": 18.0},
    # Himachal Pradesh apple belt: managed orchards have moderate diversity.
    "IN_HP": {"resilience": 12.0, "floral": 10.0},
}


def get_species_norm_for_zone(
    zone_id: str,
    norm_key: str = "resilience",
) -> float:
    """
    Return the species-count normalisation constant for a given zone.

    Parameters
    ----------
    zone_id  : str   Zone identifier, e.g. 'IN_KL_01'.
    norm_key : str   Either 'resilience' or 'floral'.

    Returns
    -------
    float  The normalisation constant.  Falls back to global defaults when no
           zone-specific override is registered.
    """
    default = SPECIES_COUNT_RESILIENCE_NORM if norm_key == "resilience" else SPECIES_COUNT_FLORAL_NORM
    if not zone_id:
        return default
    parts = zone_id.split("_")
    for length in range(len(parts), 0, -1):
        prefix = "_".join(parts[:length])
        if prefix in _ZONE_SPECIES_NORM_OVERRIDES:
            return _ZONE_SPECIES_NORM_OVERRIDES[prefix].get(norm_key, default)
    return default


RESILIENCE_SOC_OPTIMAL = 2.5
RESILIENCE_SOC_MIN = 0.5

# ──────────────────────────────────────────────────────────────────────────────
# Centralised scoring constants
# ──────────────────────────────────────────────────────────────────────────────
# Moving all calibration thresholds here makes the surface explicit and allows
# future per-zone overrides without touching scorer.py.
# Calibration sources are documented inline.
SCORING_CONSTANTS: dict[str, float] = {
    # ── Pesticide (score_pesticide_exposure) ──────────────────────────────────
    # Sigmoid midpoint at 10 ppm based on EU/EFSA pesticide residue monitoring
    # data; concentrations above 10 ppm in field runoff consistently correlate
    # with >50% bee colony stress (EFSA 2023 bee health report).
    "pesticide_ppm_midpoint": 10.0,
    "pesticide_ppm_steepness": 0.22,
    # Frequency normalised to 8 applications/month as the practical ceiling
    # for intensive Indian cotton/vegetable production (ICAR crop-protection norms).
    "pesticide_freq_max": 8.0,
    # Recency window: stress decays to zero when last application is 30+ days ago.
    "pesticide_recency_days": 30.0,

    # ── Soil fertility (score_soil_fertility) ─────────────────────────────────
    # pH optimum 6.5: global consensus (Fageria & Baligar 2008; FAO soils portal).
    # Tolerance of 1.0 pH unit means half-max stress at pH 5.5 or 7.5, matching
    # ANOMALY_THRESHOLDS ph_low_warning / ph_high_warning.
    "soil_ph_optimum": 6.5,
    "soil_ph_tolerance_steepness": 1.5,   # sigmoid steepness parameter
    "soil_ph_midpoint_deviation": 1.0,    # pH units from optimum at which stress = 0.5
    # SOC threshold: stress rises sharply below 1.5 g/kg, matching
    # ANOMALY_THRESHOLDS organic_carbon_low_warning (1.5 g/kg).
    "soil_soc_stress_threshold": 1.5,
    "soil_soc_sigmoid_midpoint": 0.5,
    "soil_soc_sigmoid_steepness": 2.5,
    # Moisture optimum 0.50 (NASA POWER GWETROOT 0–1 scale)
    # tolerance 0.30 derived from field capacity / wilting point range for
    # loam soils typical of Indian agricultural zones.
    "soil_moisture_optimum": 0.50,
    "soil_moisture_tolerance": 0.30,

    # ── Climate variability (score_climate_variability) ───────────────────────
    # Drought sigmoid midpoint 0.55: stress = 0.5 when ETP/precipitation ratio = 0.55.
    # Based on FAO aridity index classification (semi-arid threshold).
    "drought_sigmoid_midpoint": 0.55,
    "drought_sigmoid_steepness": 5.0,
    # Precipitation deficit: stress rises from 30 mm below 30-day average (matches
    # ANOMALY_THRESHOLDS rainfall_deficit_warning).
    "precip_deficit_lo_ok": 0.0,
    "precip_deficit_hi_stress": 60.0,
    # Temperature std thresholds depend on latitude (set in scorer.py).
    "temp_std_tropical_lo": 8.0,     # °C std dev, tropical zone low-stress limit
    "temp_std_tropical_hi": 20.0,
    "temp_std_temperate_lo": 4.0,
    "temp_std_temperate_hi": 14.0,
    "tropical_lat_threshold": 25.0,  # |lat| < 25° considered tropical

    # ── Nesting availability (score_nesting_availability) ────────────────────
    # Bare soil optimum range 5–30%: below 5% means dense canopy (no ground nesting),
    # above 30% means disturbed landscape (few nest sites).
    "nesting_bare_soil_hi_threshold": 0.30,
    "nesting_bare_soil_lo_threshold": 0.05,
    # Hedgerow density: stress-free above 0.30 (30% linear hedge cover per ha).
    # Threshold from UK agri-environment scheme pollinator metrics.
    "nesting_hedge_optimum": 0.30,
    "nesting_deadwood_optimum": 0.20,

    # ── Floral diversity (score_floral_diversity) ─────────────────────────────
    # NDVI threshold 0.35: below this indicates sparse vegetation with few floral
    # resources; calibrated from MODIS NDVI studies in Indian agricultural zones.
    "floral_ndvi_threshold": 0.35,
    "floral_coverage_threshold": 0.25,
    "floral_patch_diversity_threshold": 0.50,

    # ── Pollination factor (score_pollination_factor) ─────────────────────────
    # Visit ratio threshold 0.75: stress starts when observed visits are below
    # 75% of expected, based on IBRA/BeeWalk survey methodology.
    "poll_visit_ratio_threshold": 0.75,
    # Decline rate normaliser 0.55: 55% decline over 12 weeks = full stress,
    # calibrated from COLOSS winter colony loss survey data (Europe 2022).
    "poll_decline_normaliser": 0.55,
    # Flowering success threshold 0.65: below this, fruit/seed set is impaired.
    "poll_flowering_threshold": 0.65,

    # ── Wind stress (score_climate_variability) ───────────────────────────────
    # Linear ramp: no stress below 15 km/h; full stress at 25 km/h.
    # 15 km/h: bee foraging becomes erratic (COLOSS BeeBook field methods).
    # 25 km/h: complete cessation of bee flight (IBRA field guidance).
    # Weight within climate_variability: 15%, absorbed from precip_var_stress
    # (which drops from 15% to 0% — precip variance is already captured
    # by the rainfall-deficit signal and has low marginal information value).
    "wind_stress_lo_kmh": 15.0,
    "wind_stress_hi_kmh": 25.0,
}


# ──────────────────────────────────────────────────────────────────────────────
# Inter-factor interaction penalties (roadmap item 6.2)
# ──────────────────────────────────────────────────────────────────────────────
# When two stressors are simultaneously high they create a synergistic burden
# that the weighted sum of individual scores underestimates.  These penalties
# are added to overall_stress ONLY when BOTH factors exceed the activation
# threshold, ensuring low-stress zones are never penalised.
#
# Calibration rationale
# ─────────────────────
# (pesticide, floral): high pesticide + sparse forage = near-total foraging
#   failure (bees cannot find pesticide-free flowers).  Documented in
#   Woodcock et al. 2017 (Science) — combined exposure / forage loss doubled
#   colony failure rates vs either stressor alone.  Penalty: 0.08.
# (pesticide, nesting): chronic pesticide exposure impairs navigation to
#   nesting sites (sub-lethal neonicotinoid effect; Stanley et al. 2015).
#   Penalty: 0.05.
# (soil, floral): low SOC → poor nectar quality + thin vegetation → compound
#   forage deficit.  Penalty: 0.04.
#
# INTERACTION_STRESS_THRESHOLD: both factors must exceed this stress value
# for the penalty to activate.  0.70 was chosen because the empirical studies
# above document synergistic effects only in high-stress conditions.

INTERACTION_PENALTIES: dict[tuple[str, str], float] = {
    ("pesticide_exposure", "floral_diversity"):    0.08,
    ("pesticide_exposure", "nesting_availability"): 0.05,
    ("soil_fertility",     "floral_diversity"):    0.04,
}

INTERACTION_STRESS_THRESHOLD: float = 0.70

# ──────────────────────────────────────────────────────────────────────────────
# Crop Affinity Matrix (6.4)
# ──────────────────────────────────────────────────────────────────────────────

CROP_FACTOR_AFFINITY: dict[str, dict[str, float]] = {
    "apple":      {"pollination_factor": 0.55, "climate_variability": 0.25, "pesticide_exposure": 0.20},
    "mustard":    {"pesticide_exposure": 0.45, "pollination_factor": 0.35, "soil_fertility": 0.20},
    "sunflower":  {"pollination_factor": 0.50, "soil_fertility": 0.25, "pesticide_exposure": 0.25},
    "mango":      {"pollination_factor": 0.50, "climate_variability": 0.30, "floral_diversity": 0.20},
    "coffee":     {"pollination_factor": 0.45, "climate_variability": 0.30, "nesting_availability": 0.25},
    "tea":        {"climate_variability": 0.40, "soil_fertility": 0.35, "pesticide_exposure": 0.25},
    "rice":       {"climate_variability": 0.45, "soil_fertility": 0.35, "pesticide_exposure": 0.20},
    "cotton":     {"pollination_factor": 0.40, "pesticide_exposure": 0.35, "climate_variability": 0.25},
    "cardamom":   {"pollination_factor": 0.45, "climate_variability": 0.30, "soil_fertility": 0.25},
    "lychee":     {"pollination_factor": 0.55, "climate_variability": 0.25, "nesting_availability": 0.20},
    "saffron":    {"climate_variability": 0.50, "soil_fertility": 0.30, "pollination_factor": 0.20},
    "coconut":    {"climate_variability": 0.40, "pollination_factor": 0.35, "soil_fertility": 0.25},
    "bajra":      {"climate_variability": 0.45, "soil_fertility": 0.35, "pollination_factor": 0.20},
    "groundnut":  {"soil_fertility": 0.40, "climate_variability": 0.35, "pollination_factor": 0.25},
    "jowar":      {"climate_variability": 0.45, "soil_fertility": 0.40, "pesticide_exposure": 0.15},
    "ragi":       {"climate_variability": 0.40, "soil_fertility": 0.40, "pesticide_exposure": 0.20},
    "cumin":      {"pollination_factor": 0.45, "climate_variability": 0.35, "pesticide_exposure": 0.20},
    "coriander":  {"pollination_factor": 0.40, "climate_variability": 0.35, "pesticide_exposure": 0.25},
}

# ────────────────────────────────────────────────────────────────────────────────
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

OPEN_METEO_AGRO_HOURLY_VARS = [
    "relative_humidity_2m",
    "vapour_pressure_deficit",
    "soil_temperature_0cm",
    "soil_temperature_6cm",
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm",
    "soil_moisture_27_to_81cm",
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

# Crop lookup enrichment. LLM crop resolution is optional and aggressively
# cached because crop mixes change slowly compared with request frequency.
GROQ_CROP_LOOKUP_ENABLED = os.environ.get("GROQ_CROP_LOOKUP_ENABLED", "1").lower() not in {
    "0", "false", "no"
}
GROQ_CROP_LOOKUP_TIMEOUT = float(os.environ.get("GROQ_CROP_LOOKUP_TIMEOUT", "4"))
GROQ_CROP_CACHE_PRECISION = int(os.environ.get("GROQ_CROP_CACHE_PRECISION", "1"))
GROQ_CROP_CACHE_TTL_SECONDS = int(os.environ.get("GROQ_CROP_CACHE_TTL_SECONDS", str(7 * 24 * 3600)))

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
# Agromonitoring credentials + geometry  (Tier 2 fallback)
# ──────────────────────────────────────────────────────────────────────────────
AGROMONITORING_API_KEY: str = os.environ.get("AGROMONITORING_API_KEY", "")
COPERNICUS_CLIENT_ID: str = os.environ.get("COPERNICUS_CLIENT_ID", "")
COPERNICUS_CLIENT_SECRET: str = os.environ.get("COPERNICUS_CLIENT_SECRET", "")
# Half-side of the square polygon created around a lat/lon point.
# 0.0045 deg ~ 0.5 km gives a ~1 km2 field polygon (minimum for meaningful NDVI).
AGROMONITORING_POLYGON_HALF_DEG: float = 0.0045
# Look-back window for image search (days).
AGROMONITORING_IMAGE_WINDOW_DAYS: int = 30
# Maximum cloud coverage accepted when selecting a satellite image.
AGROMONITORING_MAX_CLOUD_PCT: float = 30.0


# ──────────────────────────────────────────────────────────────────────────────
# Per-zone YAML weight overrides
# Loaded once at import time from zone_weights.yaml (sibling of config.py).
# Falls back to FACTOR_WEIGHTS if the file is absent or unparseable.
# ──────────────────────────────────────────────────────────────────────────────

import os as _os
import pathlib as _pathlib

_ZONE_WEIGHTS_PATH = _pathlib.Path(__file__).parent / "zone_weights.yaml"
_ZONE_WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {}


def _load_zone_weights() -> None:
    """
    Parse zone_weights.yaml into _ZONE_WEIGHT_OVERRIDES (longest-prefix lookup).

    Raises
    ------
    ValueError
        At import time if any zone's weights do not sum to 1.0 (±1e-6) or if
        any weight key is not present in the global FACTOR_WEIGHTS dict.  Fail
        fast at startup is preferable to silently corrupted scores at request time.
    """
    global _ZONE_WEIGHT_OVERRIDES
    if not _ZONE_WEIGHTS_PATH.exists():
        return
    try:
        import yaml  # PyYAML optional dependency
        with open(_ZONE_WEIGHTS_PATH) as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:
        # YAML parse failure is non-fatal; log and continue with empty overrides.
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "zone_weights.yaml parse failed — using global defaults: %s", exc
        )
        _ZONE_WEIGHT_OVERRIDES = {}
        return

    expected_keys = set(FACTOR_WEIGHTS.keys())
    validated: dict[str, dict[str, float]] = {}

    for zone_prefix, weights in data.items():
        if not isinstance(weights, dict):
            raise ValueError(
                f"zone_weights.yaml: zone '{zone_prefix}' must map to a dict of weights, "
                f"got {type(weights).__name__!r}."
            )
        unknown_keys = set(weights.keys()) - expected_keys
        if unknown_keys:
            raise ValueError(
                f"zone_weights.yaml: zone '{zone_prefix}' contains unknown factor keys: "
                f"{sorted(unknown_keys)}.  Valid keys are: {sorted(expected_keys)}."
            )
        missing_keys = expected_keys - set(weights.keys())
        if missing_keys:
            raise ValueError(
                f"zone_weights.yaml: zone '{zone_prefix}' is missing factor keys: "
                f"{sorted(missing_keys)}.  All six factors must be specified."
            )
        total = sum(float(v) for v in weights.values())
        if abs(total - 1.0) >= 1e-6:
            raise ValueError(
                f"zone_weights.yaml: zone '{zone_prefix}' weights sum to {total:.8f}, "
                f"expected 1.0 (±1e-6).  Adjust values so they sum exactly to 1.0."
            )
        validated[zone_prefix] = {k: float(v) for k, v in weights.items()}

    _ZONE_WEIGHT_OVERRIDES = validated


_load_zone_weights()


def get_factor_weights_for_zone(zone_id: str, geo_profile: dict = None) -> dict[str, float]:
    """
    Return the factor weights for a given zone_id.
    Longest-prefix match against zone_weights.yaml; falls back to dynamic geo_profile.
    """
    if zone_id:
        parts = zone_id.split("_")
        for length in range(len(parts), 0, -1):
            prefix = "_".join(parts[:length])
            if prefix in _ZONE_WEIGHT_OVERRIDES:
                return _ZONE_WEIGHT_OVERRIDES[prefix]

    # Dynamic profile is used as a fallback
    if geo_profile and 'factor_weights' in geo_profile:
        return geo_profile['factor_weights']

    return FACTOR_WEIGHTS

# ──────────────────────────────────────────────────────────────────────────────
# Agro-climatic zone threshold overrides
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

    try:
        from history_store import get_seasonal_threshold_overrides
        seasonal = get_seasonal_threshold_overrides(zone_id)
        for key, value in seasonal.items():
            if key in merged:
                merged[key] = value
    except Exception:
        pass

    return merged


def _validate_zone_threshold_overrides() -> None:
    """
    Fix 6.3: Validate that every key in _AGRO_ZONE_THRESHOLD_OVERRIDES exists in
    ANOMALY_THRESHOLDS at module load time. A typo’d override key silently has no
    effect, which is harder to detect than a startup error.

    Raises ValueError if any override key is not in ANOMALY_THRESHOLDS.
    """
    valid_keys = set(ANOMALY_THRESHOLDS.keys())
    for zone_prefix, overrides in _AGRO_ZONE_THRESHOLD_OVERRIDES.items():
        unknown = set(overrides.keys()) - valid_keys
        if unknown:
            raise ValueError(
                f"_AGRO_ZONE_THRESHOLD_OVERRIDES['{zone_prefix}'] contains unknown threshold keys: "
                f"{sorted(unknown)}. Valid keys are: {sorted(valid_keys)}."
            )


_validate_zone_threshold_overrides()
