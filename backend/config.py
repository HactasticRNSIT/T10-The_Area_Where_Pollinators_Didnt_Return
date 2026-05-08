

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
    # Karnataka — Deccan Plateau oilseeds & pulses
    "IN_KA": {
        "sunflower":  0.90,  # primary bee-dependent oilseed of Karnataka
        "cotton":     0.15,  # Bt cotton, some insect pollination
        "red gram":   0.40,
        "groundnut":  0.55,
        "sorghum":    0.05,
    },
    # Rajasthan — arid drylands mustard & cumin belt
    "IN_RJ": {
        "mustard":    0.80,  # #1 crop; huge migratory bee demand Feb–Mar
        "cumin":      0.65,
        "coriander":  0.60,
        "wheat":      0.10,
        "sesame":     0.50,
    },
    # Uttar Pradesh — Malihabad mango cluster
    "IN_UP": {
        "mango":      0.75,  # bee-critical for fruit set
        "guava":      0.55,
        "sugarcane":  0.02,  # wind-pollinated
        "wheat":      0.10,
        "lychee":     0.80,
    },
    # Gujarat — cotton & groundnut semi-arid zone
    "IN_GJ": {
        "cotton":     0.15,  # Bt cotton; limited but present bee use
        "groundnut":  0.55,  # significant bee benefit
        "castor":     0.35,
        "wheat":      0.10,
        "sesame":     0.50,
    },
    # West Bengal — rice & jute floodplain
    "IN_WB": {
        "rice":       0.03,  # primarily wind/self-pollinated
        "jute":       0.05,
        "mustard":    0.80,  # rabi season crop; bee-dependent
        "vegetables": 0.45,
        "watermelon": 0.90,
    },
    # Kerala — spice coast tropical evergreen
    "IN_KL": {
        "cardamom":    0.95,  # almost entirely bee-pollinated
        "black pepper": 0.60,
        "coffee":      0.55,
        "coconut":     0.30,
        "rubber":      0.05,
    },
    # Himachal Pradesh — temperate apple belt
    "IN_HP": {
        "apple":      0.95,  # managed honeybee hives placed in orchards
        "cherry":     0.90,
        "plum":       0.70,
        "pear":       0.75,
        "potato":     0.10,
    },
    # Maharashtra — Vidarbha orange & soybean belt
    "IN_MH": {
        "orange":     0.75,
        "cotton":     0.15,
        "soybean":    0.25,
        "sorghum":    0.05,
        "pomegranate": 0.60,
    },
    # Madhya Pradesh — semi-arid sesame & soybean
    "IN_MP": {
        "sesame":     0.50,
        "soybean":    0.25,
        "wheat":      0.10,
        "chickpea":   0.20,
        "lentils":    0.20,
    },
    # Bihar — alluvial lychee & mango belt
    "IN_BR": {
        "lychee":     0.80,
        "mango":      0.75,
        "wheat":      0.10,
        "maize":      0.05,
        "banana":     0.10,
    },
    # USA Central Valley (California almonds, stone fruit)
    "FARM_G": {
        "almonds":    1.00,
        "stone fruit": 0.85,
        "tomatoes":   0.55,
        "grapes":     0.10,
        "canola":     0.70,
    },
    # USA Midwest Corn Belt
    "FARM_H": {
        "maize":      0.05,
        "soybean":    0.25,
        "sunflower":  0.65,
        "canola":     0.70,
        "wheat":      0.10,
    },
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
