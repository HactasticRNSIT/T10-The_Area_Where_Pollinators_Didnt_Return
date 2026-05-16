

import math
import hashlib
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _zone_seed(lat: float, lon: float) -> float:
    """
    Produce a stable float in [0, 1) that is unique to this (lat, lon) pair.
    Used to create repeatable pseudo-random variation across zones.
    """
    key = f"{lat:.4f}:{lon:.4f}"
    digest = hashlib.md5(key.encode()).hexdigest()
    # Use first 8 hex chars → 32-bit integer → normalise
    return int(digest[:8], 16) / 0xFFFFFFFF


def _jitter(seed: float, offset: float, amplitude: float) -> float:
    """Deterministic jitter: seed shifted by offset, scaled by amplitude."""
    return math.sin(seed * 17.3 + offset) * amplitude


# ──────────────────────────────────────────────────────────────────────────────
# SoilGrids mock
# ──────────────────────────────────────────────────────────────────────────────

def get_mock_soil_data(lat: float, lon: float) -> dict[str, Any]:
    """
    Return plausible soil property values for a given coordinate.

    Real SoilGrids units:
        phh2o        → pH × 10  (stored as integer, e.g. 65 = pH 6.5)
        nitrogen     → cg/kg
        soc (SOC)    → dg/kg  (soil organic carbon)
        bdod         → cg/cm³ (bulk density)
        clay         → g/kg
        sand         → g/kg
        silt         → g/kg
    We store in scientist-friendly units directly.
    """
    s = _zone_seed(lat, lon)

    # pH: bell-curve around 6.2, range [4.8, 8.0]
    ph = 6.2 + _jitter(s, 0.0, 1.4)
    ph = max(4.8, min(8.0, ph))

    # Organic carbon: g/kg, range [0.5, 3.5]
    soc = 1.8 + _jitter(s, 1.5, 1.2)
    soc = max(0.5, min(3.5, soc))

    # Nitrogen: g/kg, range [0.3, 2.5]
    nitrogen = 1.2 + _jitter(s, 3.1, 0.9)
    nitrogen = max(0.3, min(2.5, nitrogen))

    # Phosphorus: mg/kg (Olsen P), range [5, 45]
    phosphorus = 22.0 + _jitter(s, 4.7, 16.0)
    phosphorus = max(5.0, min(45.0, phosphorus))

    # Bulk density: g/cm³, range [1.0, 1.8]
    bulk_density = 1.35 + _jitter(s, 6.2, 0.35)
    bulk_density = max(1.0, min(1.8, bulk_density))

    # Clay content: g/kg, range [50, 450]
    clay = 200 + _jitter(s, 7.8, 150)
    clay = max(50, min(450, clay))

    # Compaction index: 0–1 (derived from bulk density)
    compaction = (bulk_density - 1.0) / 0.8

    return {
        "source":       "mock_soilgrids",
        "ph":           round(ph, 2),
        "organic_carbon_g_per_kg": round(soc, 2),
        "nitrogen_g_per_kg":       round(nitrogen, 2),
        "phosphorus_mg_per_kg":    round(phosphorus, 1),
        "bulk_density_g_per_cm3":  round(bulk_density, 3),
        "clay_g_per_kg":           round(clay, 1),
        "compaction_index":        round(compaction, 3),
    }






def get_mock_visitation_data(
    lat: float,
    lon: float,
    ndvi: dict[str, Any],
    pesticide: dict[str, Any],
    climate: dict[str, Any],
    gbif: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a deterministic pollinator visitation signal from the same drivers
    used by the scorer.

    The problem statement is about declining and irregular pollinator visits,
    so this keeps the mock layer internally consistent instead of generating
    unrelated random-looking values.
    """
    s = _zone_seed(lat, lon)

    ndvi_val = ndvi.get("ndvi", 0.5)
    flowering = ndvi.get("flowering_coverage", 0.35)
    species_count = gbif.get("species_count", 8)
    pesticide_ppm = pesticide.get("usage_ppm", 5.0)
    pesticide_freq = pesticide.get("applications_per_month", 2)
    drought_index = climate.get("drought_index", 0.35)
    if drought_index is None:
        drought_index = 0.4

    habitat_quality = max(0.0, min(1.0, ndvi_val * 0.45 + flowering * 0.35 + min(species_count / 20.0, 1.0) * 0.20))
    pesticide_pressure = max(0.0, min(1.0, pesticide_ppm / 20.0 * 0.65 + pesticide_freq / 8.0 * 0.35))
    climate_pressure = max(0.0, min(1.0, float(drought_index)))

    stress = max(0.0, min(1.0, pesticide_pressure * 0.45 + (1.0 - habitat_quality) * 0.35 + climate_pressure * 0.20))
    baseline_visits = 18.0 + habitat_quality * 22.0
    current_visits = max(0.5, baseline_visits * (1.0 - stress * 0.82))
    decline_rate = max(0.0, min(0.9, stress * 0.55 + max(0.0, pesticide_pressure - 0.45) * 0.25))

    weekly_visits = []
    for i in range(12):
        age = 11 - i
        seasonal_wave = math.sin(s * 9.1 + i * 0.85) * 0.12
        recovery_noise = math.sin(s * 15.7 + i * 1.6) * stress * 0.18
        value = current_visits * (1.0 + decline_rate * age / 11.0 + seasonal_wave + recovery_noise)
        weekly_visits.append(round(max(0.2, value), 2))

    expected_visits = round(baseline_visits, 2)
    avg_visits = round(sum(weekly_visits[-4:]) / 4.0, 2)
    expected_ratio = round(avg_visits / expected_visits, 3) if expected_visits else 0.0
    timing_disruption = max(0.0, min(1.0, stress * 0.70 + abs(math.sin(s * 21.0)) * 0.20))
    flowering_success = max(0.05, min(0.98, flowering * 0.55 + expected_ratio * 0.35 + (1.0 - timing_disruption) * 0.10))
    recovery_volatility = max(0.0, min(1.0, stress * 0.55 + abs(math.sin(s * 17.0)) * 0.25))

    return {
        "source": "modelled_visitation",
        "avg_visitations_per_hour": avg_visits,
        "expected_visitations_per_hour": expected_visits,
        "visitation_ratio": expected_ratio,
        "twelve_week_visits_per_hour": weekly_visits,
        "decline_rate_12w": round(decline_rate, 3),
        "pollination_timing_disruption": round(timing_disruption, 3),
        "flowering_success_rate": round(flowering_success, 3),
        "recovery_volatility": round(recovery_volatility, 3),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Full mock bundle (used when all real sources fail)
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# Fix 9: Dual-source pesticide proxy (replaces get_mock_pesticide_data)
# Source A: GOI State-wise Demand 2025-26 (MT formulation) -- Indian zones
# Source B: UN FAO FAOSTAT 2023 (tonnes AI) -- global zones
# ──────────────────────────────────────────────────────────────────────────────

_STATE_PESTICIDE_DEMAND_MT: dict[str, float] = {
    "IN_AP": 1760.0, "IN_BR": 1295.0, "IN_CG": 1850.0, "IN_GA":   33.06,
    "IN_GJ": 2078.0, "IN_HR": 4215.0, "IN_HP":  453.5, "IN_JH": 1470.2,
    "IN_KA": 2100.0, "IN_KL":  509.6, "IN_MP":  765.9, "IN_MH":10104.0,
    "IN_OD": 1405.0, "IN_PB": 5355.0, "IN_RJ": 2020.0, "IN_TN": 2175.0,
    "IN_TG": 6469.0, "IN_UP":14980.0, "IN_UK":  217.2, "IN_WB": 4570.0,
    "IN_AR":    3.6, "IN_AS":  640.9, "IN_MN":  43.33, "IN_MZ":   48.67,
    "IN_NL":  24.05, "IN_JK": 8828.5,
}

_COUNTRY_FAO_TONNES_2023: dict[str, float] = {
    "USA": 429501.0, "BRA": 800652.0, "CHN": 217996.0,
    "ARG": 262507.0, "AUS": 182264.0, "FRA":  67621.0,
    "DEU":  46038.0, "GBR":  14688.0,
}

_ZONE_COUNTRY_MAP: dict[str, str] = {
    "FARM_G": "USA", "FARM_H": "USA",
    "BR": "BRA", "CN": "CHN", "FR": "FRA",
    "DE": "DEU", "GB": "GBR", "AU": "AUS",
}

_CROP_PESTICIDE_TYPE: dict[str, tuple[str, float]] = {
    "apple":        ("neonicotinoid",   1.40),
    "cherry":       ("neonicotinoid",   1.40),
    "almonds":      ("neonicotinoid",   1.40),
    "canola":       ("neonicotinoid",   1.40),
    "stone fruit":  ("neonicotinoid",   1.40),
    "cotton":       ("organophosphate", 1.20),
    "rice":         ("organophosphate", 1.20),
    "orange":       ("organophosphate", 1.20),
    "pomegranate":  ("organophosphate", 1.20),
    "sunflower":    ("pyrethroid",      1.10),
    "mustard":      ("pyrethroid",      1.10),
    "wheat":        ("pyrethroid",      1.10),
    "soybean":      ("pyrethroid",      1.10),
    "mango":        ("pyrethroid",      1.10),
    "groundnut":    ("pyrethroid",      1.10),
    "sesame":       ("pyrethroid",      1.10),
    "maize":        ("pyrethroid",      1.10),
    "tomatoes":     ("pyrethroid",      1.10),
    "cardamom":     ("biopesticide",    0.60),
    "coffee":       ("biopesticide",    0.60),
    "black pepper": ("biopesticide",    0.60),
    "rubber":       ("biopesticide",    0.60),
    "default":      ("pyrethroid",      1.10),
}


def compute_pesticide_proxy(zone_id: str) -> dict[str, Any]:
    """Derive pesticide data from real regional statistics + crop profiles.
    Priority: Indian state data (Excel 2025-26)
             -> FAO country data (FAOSTAT 2023)
             -> conservative national-average fallback.
    """
    from config import get_crop_dependency_for_zone

    demand_mt = None
    source_label = "state_statistics_and_crop_model"

    if zone_id:
        parts = zone_id.split("_")
        for length in range(len(parts), 0, -1):
            prefix = "_".join(parts[:length])
            if prefix in _STATE_PESTICIDE_DEMAND_MT:
                demand_mt = _STATE_PESTICIDE_DEMAND_MT[prefix]
                break
        if demand_mt is None:
            for length in range(len(parts), 0, -1):
                prefix = "_".join(parts[:length])
                cc = _ZONE_COUNTRY_MAP.get(prefix)
                if cc and cc in _COUNTRY_FAO_TONNES_2023:
                    demand_mt = _COUNTRY_FAO_TONNES_2023[cc] / 28.0
                    source_label = "fao_country_statistics_and_crop_model"
                    break

    if demand_mt is None:
        demand_mt = 2000.0

    usage_ppm = round(max(1.0, min(15.0, demand_mt / 800.0)), 2)
    if usage_ppm < 3.0:
        apps = 1
    elif usage_ppm < 6.0:
        apps = 3
    elif usage_ppm < 10.0:
        apps = 5
    else:
        apps = 7

    crops = get_crop_dependency_for_zone(zone_id)
    dominant_crop = max(crops, key=crops.get) if crops else "default"
    p_type, toxicity = _CROP_PESTICIDE_TYPE.get(dominant_crop, _CROP_PESTICIDE_TYPE["default"])

    return {
        "source":                      source_label,
        "state_demand_mt_reference":   round(demand_mt, 2),
        "usage_ppm":                   usage_ppm,
        "applications_per_month":      apps,
        "days_since_last_application": 14,
        "pesticide_type":              p_type,
        "toxicity_multiplier":         toxicity,
        "_fetch_error":                None,
    }

def get_full_mock_bundle(lat: float, lon: float) -> dict[str, Any]:
    """
    Return all mock data in a single call.  Used as the complete fallback
    when live API calls fail during development or testing.
    """
    neutral_ndvi = {
        "source":"agromonitoring_unavailable","ndvi":0.45,"flowering_coverage":0.30,
        "patch_diversity":0.40,"hedgerow_density":0.20,"dead_wood_index":0.18,
        "bare_soil_fraction":0.25,"disturbance_score":0.30,"decline_rate_12w":0.10,
    }
    bundle = {
        "soil":      get_mock_soil_data(lat, lon),
        "ndvi":      neutral_ndvi,
        "pesticide": compute_pesticide_proxy(""),
    }
    bundle["climate"] = {
        "source": "mock_open_meteo",
        "temp_mean_c": 20.0,
        "temp_std_c": 4.0,
        "total_precipitation_mm": 50.0,
        "precip_std_mm": 3.0,
        "drought_index": 0.2,
    }
    bundle["gbif"] = {"source": "mock_gbif", "species_count": 15}
    bundle["visitation"] = get_mock_visitation_data(
        lat, lon, bundle["ndvi"], bundle["pesticide"], bundle["climate"], bundle["gbif"]
    )
    return bundle
