

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


# ──────────────────────────────────────────────────────────────────────────────
# NDVI / Floral diversity mock
# ──────────────────────────────────────────────────────────────────────────────

def get_mock_ndvi_data(lat: float, lon: float) -> dict[str, Any]:
    """
    Return mocked NDVI and floral diversity metrics.

    NDVI (Normalised Difference Vegetation Index):
        Range -1 to 1; agricultural cropland typically 0.2–0.8.
    Flowering coverage: fraction 0–1.
    """
    s = _zone_seed(lat, lon)

    # NDVI: range [0.15, 0.85]
    ndvi = 0.50 + _jitter(s, 2.3, 0.28)
    ndvi = max(0.15, min(0.85, ndvi))

    # Flowering coverage: 0–1
    flower_cov = 0.35 + _jitter(s, 5.1, 0.25)
    flower_cov = max(0.02, min(0.90, flower_cov))

    # Vegetation patch diversity (Shannon H proxy, 0–1)
    patch_diversity = 0.45 + _jitter(s, 8.4, 0.30)
    patch_diversity = max(0.05, min(1.0, patch_diversity))

    # Hedgerow density: fraction of field perimeter with hedgerows, 0–1
    hedgerow_density = 0.30 + _jitter(s, 9.9, 0.25)
    hedgerow_density = max(0.0, min(1.0, hedgerow_density))

    # Dead wood index: 0–1
    dead_wood = 0.20 + _jitter(s, 11.2, 0.15)
    dead_wood = max(0.0, min(1.0, dead_wood))

    # Bare soil fraction: 0–1
    bare_soil = 0.25 + _jitter(s, 12.7, 0.20)
    bare_soil = max(0.0, min(0.75, bare_soil))

    # Disturbance score (tillage, traffic, etc.): 0–1
    disturbance = 0.35 + _jitter(s, 14.3, 0.25)
    disturbance = max(0.0, min(1.0, disturbance))

    return {
        "source":            "mock_modis_ndvi",
        "ndvi":              round(ndvi, 3),
        "flowering_coverage": round(flower_cov, 3),
        "patch_diversity":   round(patch_diversity, 3),
        "hedgerow_density":  round(hedgerow_density, 3),
        "dead_wood_index":   round(dead_wood, 3),
        "bare_soil_fraction": round(bare_soil, 3),
        "disturbance_score": round(disturbance, 3),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Pesticide usage mock
# ──────────────────────────────────────────────────────────────────────────────

def get_mock_pesticide_data(lat: float, lon: float) -> dict[str, Any]:
    """
    Return mocked pesticide usage data for a zone.

    There is no public free API for field-level pesticide tracking;
    this mock provides internally consistent test data.
    """
    s = _zone_seed(lat, lon)

    # Usage in ppm (parts per million), range [0.5, 25]
    usage_ppm = 5.0 + _jitter(s, 3.3, 9.5)
    usage_ppm = max(0.5, min(25.0, usage_ppm))

    # Applications per month, integer 0–8
    raw_freq = 2.5 + _jitter(s, 6.6, 2.5)
    applications_per_month = max(0, min(8, round(raw_freq)))

    # Days since last application, range [1, 45]
    raw_days = 14 + _jitter(s, 9.9, 12)
    days_since_last = max(1, min(45, round(raw_days)))

    # Pesticide type (affects toxicity weight)
    type_seed = (s + 0.13) % 1.0
    if type_seed < 0.35:
        pesticide_type = "neonicotinoid"   # high bee toxicity
        toxicity_multiplier = 1.40
    elif type_seed < 0.65:
        pesticide_type = "pyrethroid"      # moderate toxicity
        toxicity_multiplier = 1.10
    elif type_seed < 0.85:
        pesticide_type = "organophosphate" # moderate-high
        toxicity_multiplier = 1.20
    else:
        pesticide_type = "biopesticide"    # low toxicity
        toxicity_multiplier = 0.60

    return {
        "source":                "mock_pesticide",
        "usage_ppm":             round(usage_ppm, 2),
        "applications_per_month": applications_per_month,
        "days_since_last_application": days_since_last,
        "pesticide_type":        pesticide_type,
        "toxicity_multiplier":   toxicity_multiplier,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Full mock bundle (used when all real sources fail)
# ──────────────────────────────────────────────────────────────────────────────

def get_full_mock_bundle(lat: float, lon: float) -> dict[str, Any]:
    """
    Return all mock data in a single call.  Used as the complete fallback
    when live API calls fail during development or testing.
    """
    return {
        "soil":      get_mock_soil_data(lat, lon),
        "ndvi":      get_mock_ndvi_data(lat, lon),
        "pesticide": get_mock_pesticide_data(lat, lon),
    }
