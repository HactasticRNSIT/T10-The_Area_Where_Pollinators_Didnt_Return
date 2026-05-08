

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

    # Groq LLM inference
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}

# ──────────────────────────────────────────────────────────────────────────────
# Factor weights (must sum to 1.0)
# ──────────────────────────────────────────────────────────────────────────────
FACTOR_WEIGHTS = {
    "pesticide_exposure":  0.35,
    "soil_fertility":      0.25,
    "floral_diversity":    0.20,
    "climate_variability": 0.12,
    "nesting_availability": 0.08,
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

    # Nesting
    "bare_soil_warning":           0.30,   # fraction 0–1
    "bare_soil_critical":          0.55,
    "disturbance_warning":         0.50,
    "disturbance_critical":        0.75,
}

# ──────────────────────────────────────────────────────────────────────────────
# Crop pollination dependency (fraction of yield dependent on pollinators)
# Used to compute crop_risk from the activity score
# ──────────────────────────────────────────────────────────────────────────────
CROP_POLLINATION_DEPENDENCY = {
    "almonds":     1.00,  # 100% dependent
    "blueberries": 0.90,
    "canola":      0.70,
    "sunflower":   0.65,
    "wheat":       0.10,
    "maize":       0.05,
}

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
    "windspeed_10m_max",
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
