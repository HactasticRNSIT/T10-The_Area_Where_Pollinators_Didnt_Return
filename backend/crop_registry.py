"""
crop_registry.py
================
Static crop registry for Indian states with pollinator-dependency weights.

Data sources:
  - ICAR (Indian Council of Agricultural Research) crop statistics
  - Ministry of Agriculture & Farmers Welfare, India — Crop Area / Production data
  - FAO pollinator dependency fractions (Klein et al. 2007; Aizen et al. 2009)
  - State Agriculture Department annual reports

Pollinator dependency (0.0–1.0):
  Fraction of yield reduction expected if pollinators were completely removed.
    0.00 – 0.10 : wind- or self-pollinated — bees give negligible direct yield gain
    0.10 – 0.40 : moderate — bees improve fruit set / grain quality noticeably
    0.40 – 0.70 : high — pollinator loss causes significant production decline
    0.70 – 1.00 : very high — crop nearly or fully dependent on pollinators

These are state-level averages.  Actual values vary by cultivar, season, and
management.  Reported as "coarse literature-informed estimates".

Nominatim returns Indian state names in English (title-cased).  All keys here
are stored lower-cased and looked up case-insensitively.
"""

from typing import Dict

# ---------------------------------------------------------------------------
# Master registry  (state lower-cased → {crop: dependency})
# ---------------------------------------------------------------------------
INDIA_STATE_CROP_REGISTRY: Dict[str, Dict[str, float]] = {

    # ── Arid / Semi-Arid ────────────────────────────────────────────────────
    "rajasthan": {
        "mustard":    0.80,   # Cross-pollination raises yield 20–30 %
        "bajra":      0.35,   # Wind + insect; bees improve grain filling
        "cumin":      0.65,   # Almost entirely bee-pollinated (Apis mellifera)
        "coriander":  0.55,   # Moderate-high; Apis dorsata key pollinator
        "wheat":      0.10,   # Wind-pollinated; marginal bee enhancement
        "cotton":     0.15,   # Largely self-pollinating; bees raise lint index
    },
    "gujarat": {
        "cotton":     0.15,
        "groundnut":  0.40,   # Moderate; bees increase pod-set by ~15 %
        "castor":     0.20,   # Wind-primary + some insect transfer
        "sesame":     0.45,   # Moderate; Apis cerana preferred visitor
        "bajra":      0.35,
        "wheat":      0.10,
    },

    # ── Wheat / Rice Belt ───────────────────────────────────────────────────
    "punjab": {
        "wheat":      0.10,
        "rice":       0.03,   # Self-pollinated
        "cotton":     0.15,
        "maize":      0.05,   # Wind-pollinated
        "mustard":    0.80,
        "sunflower":  0.65,   # High; Helianthus is bee-pollinated for seed set
    },
    "haryana": {
        "wheat":      0.10,
        "rice":       0.03,
        "mustard":    0.80,
        "sugarcane":  0.05,   # Vegetatively propagated in practice
        "cotton":     0.15,
        "sunflower":  0.65,
    },
    "uttar pradesh": {
        "wheat":      0.10,
        "rice":       0.03,
        "sugarcane":  0.05,
        "potato":     0.20,   # Bees improve tuber uniformity and early set
        "mustard":    0.80,
        "lychee":     0.90,   # Litchi sinensis — almost exclusively bee-pollinated
    },
    "bihar": {
        "rice":       0.03,
        "wheat":      0.10,
        "maize":      0.05,
        "sugarcane":  0.05,
        "potato":     0.20,
        "lychee":     0.90,   # Bihar produces ~70 % of India's lychee
    },
    "jharkhand": {
        "rice":       0.03,
        "maize":      0.05,
        "wheat":      0.10,
        "oilseeds":   0.50,   # Mixed (mustard, sunflower, sesame)
        "pulses":     0.35,   # Arhar/tur, chickpea
        "vegetables": 0.35,
    },

    # ── Central India ───────────────────────────────────────────────────────
    "madhya pradesh": {
        "soybean":    0.45,   # Self-compatible but bees improve pod-set 10–20 %
        "wheat":      0.10,
        "rice":       0.03,
        "maize":      0.05,
        "cotton":     0.15,
        "pulses":     0.35,   # Chickpea, lentil, arhar
    },
    "chhattisgarh": {
        "rice":       0.03,
        "maize":      0.05,
        "wheat":      0.10,
        "soybean":    0.45,
        "groundnut":  0.40,
        "pulses":     0.35,
    },

    # ── Maharashtra / Deccan ────────────────────────────────────────────────
    "maharashtra": {
        "cotton":     0.15,
        "sugarcane":  0.05,
        "soybean":    0.45,
        "onion":      0.75,   # Seed-crop production fully bee-dependent
        "grapes":     0.25,   # Table grapes partly wind; bees improve berry set
        "jowar":      0.05,   # Sorghum — wind-pollinated
    },

    # ── Karnataka / South Deccan ────────────────────────────────────────────
    "karnataka": {
        "rice":       0.03,
        "ragi":       0.05,   # Finger millet — wind-pollinated
        "cotton":     0.15,
        "sugarcane":  0.05,
        "coffee":     0.70,   # Coffea arabica in Coorg — bee-pollinated
        "coconut":    0.30,   # Wind + Apis dorsata; bees improve nut set 10–15 %
        "sunflower":  0.65,
    },

    # ── Andhra Pradesh / Telangana ──────────────────────────────────────────
    "andhra pradesh": {
        "rice":       0.03,
        "groundnut":  0.40,
        "cotton":     0.15,
        "sugarcane":  0.05,
        "chilli":     0.30,   # Capsicum — bees and other insects improve fruit set
        "maize":      0.05,
    },
    "telangana": {
        "rice":       0.03,
        "cotton":     0.15,
        "maize":      0.05,
        "soybean":    0.45,
        "sunflower":  0.65,
        "groundnut":  0.40,
    },

    # ── Tamil Nadu ──────────────────────────────────────────────────────────
    "tamil nadu": {
        "rice":       0.03,
        "sugarcane":  0.05,
        "cotton":     0.15,
        "groundnut":  0.40,
        "coconut":    0.30,
        "banana":     0.15,   # Self-compatible; bees improve fruit quality
    },

    # ── Kerala (Spice Coast) ────────────────────────────────────────────────
    "kerala": {
        "coconut":       0.30,
        "rubber":        0.05,   # Primarily vegetative/wind; some insect
        "tea":           0.70,   # Seed set almost fully bee-dependent
        "black pepper":  0.60,   # Apis cerana is primary pollinator in ghats
        "cardamom":      0.85,   # Very high; Apis cerana essential in Idukki
        "rice":          0.03,
    },

    # ── West Bengal / Eastern ───────────────────────────────────────────────
    "west bengal": {
        "rice":       0.03,
        "jute":       0.05,   # Self-pollinated
        "potato":     0.20,
        "mustard":    0.80,
        "wheat":      0.10,
        "vegetables": 0.35,
    },
    "odisha": {
        "rice":       0.03,
        "groundnut":  0.40,
        "sugarcane":  0.05,
        "coconut":    0.30,
        "pulses":     0.35,
        "oilseeds":   0.50,
    },

    # ── North-East India ────────────────────────────────────────────────────
    "assam": {
        "tea":        0.70,   # Camellia sinensis — high bee dependency for seed
        "rice":       0.03,
        "jute":       0.05,
        "coconut":    0.30,
        "mustard":    0.80,
        "oilseeds":   0.50,
    },
    "meghalaya": {
        "rice":       0.03,
        "maize":      0.05,
        "potato":     0.20,
        "ginger":     0.40,   # Zingiber; bees improve rhizome quality
        "turmeric":   0.35,
        "areca nut":  0.50,   # Betel nut — insect pollinated
    },
    "nagaland": {
        "rice":       0.03,
        "maize":      0.05,
        "vegetables": 0.35,
        "oilseeds":   0.50,
        "pulses":     0.35,
        "ginger":     0.40,
    },
    "manipur": {
        "rice":       0.03,
        "maize":      0.05,
        "vegetables": 0.35,
        "oilseeds":   0.50,
        "pulses":     0.35,
        "black pepper": 0.60,
    },

    # ── Hill States (Himalayan) ─────────────────────────────────────────────
    "himachal pradesh": {
        "apple":      0.95,   # Honeybees (managed hives) essential for commercial orchards
        "cherry":     0.90,   # Prunus — bee-pollinated; poor set without pollinators
        "pear":       0.85,
        "plum":       0.80,
        "wheat":      0.10,
        "maize":      0.05,
    },
    "uttarakhand": {
        "rice":       0.03,
        "wheat":      0.10,
        "maize":      0.05,
        "apple":      0.95,
        "potato":     0.20,
        "tea":        0.70,
    },

    # ── Jammu & Kashmir ─────────────────────────────────────────────────────
    "jammu and kashmir": {
        "apple":      0.95,
        "cherry":     0.90,
        "almond":     0.98,   # Prunus dulcis — requires cross-pollination
        "walnut":     0.20,   # Wind-pollinated; bees have minor role
        "saffron":    0.70,   # Crocus sativus — bee-pollinated for corm quality
        "rice":       0.03,
    },
    # Alternate Nominatim spelling
    "jammu & kashmir": {
        "apple":      0.95,
        "cherry":     0.90,
        "almond":     0.98,
        "walnut":     0.20,
        "saffron":    0.70,
        "rice":       0.03,
    },

    # ── Goa ─────────────────────────────────────────────────────────────────
    "goa": {
        "coconut":    0.30,
        "cashew":     0.60,   # Anacardium — bees give significant yield increase
        "rice":       0.03,
        "sugarcane":  0.05,
        "vegetables": 0.35,
        "areca nut":  0.50,
    },
}


def get_crops_for_state(state_name: str) -> Dict[str, float] | None:
    """
    Look up crop-dependency dict for a given state name.

    Parameters
    ----------
    state_name : str
        State name as returned by Nominatim (any case).

    Returns
    -------
    dict | None
        Crop→dependency mapping if the state is in the registry, else None.
    """
    if not state_name:
        return None
    return INDIA_STATE_CROP_REGISTRY.get(state_name.strip().lower())
