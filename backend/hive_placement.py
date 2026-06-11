"""
hive_placement.py — Roadmap item 3.4
=====================================
Structured hive-placement recommendations for high pollinator-dependent crops.

Data sources
------------
- ICAR Honey Bee Research Station, Karnal — recommended colony densities for
  Indian field crops (Bulletin 2019).
- Delaplane & Mayer (2000) "Crop Pollination by Bees" — hives/ha ranges.
- Abrol (2012) "Pollination Biology" — Apis cerana foraging distances in India.
- Klein et al. (2007) FAO dependency fractions — threshold logic.

Coverage
--------
All crops with dependency >= 0.60 from the INDIA_STATE_CROP_REGISTRY plus
any crop explicitly listed below that reaches 0.60 in any state.

API
---
    from hive_placement import get_hive_placement_advice

    advice = get_hive_placement_advice(
        crops={"apple": 0.95, "wheat": 0.10},
        overall_stress=0.62,
    )
    # Returns list[dict] — one entry per crop with dependency >= 0.60,
    # sorted by crop dependency descending.  Empty list if no crop qualifies.
"""

from __future__ import annotations

from typing import Any

__all__ = ["get_hive_placement_advice"]


# ──────────────────────────────────────────────────────────────────────────────
# Threshold: only recommend hives for crops with meaningful dependency.
# 0.60 is chosen to cover cardamom (0.60) and exclude cotton (0.15).
# ──────────────────────────────────────────────────────────────────────────────
_DEPENDENCY_THRESHOLD = 0.60


# ──────────────────────────────────────────────────────────────────────────────
# Placement specifications
# Keys must be lowercase and match keys used in INDIA_STATE_CROP_REGISTRY
# and ZONE_DEFAULT_CROP_MAPPINGS (config.py).
# ──────────────────────────────────────────────────────────────────────────────
# Field meanings:
#   species         : Preferred managed bee species for India (primary / secondary)
#   hives_per_ha    : Recommended colony density for commercial pollination
#   max_forage_m    : Effective foraging radius in metres for placement spacing
#   timing_note     : When to introduce hives relative to crop phenology
#   placement_tip   : Key field-level guidance (shelter, orientation, water)
# ──────────────────────────────────────────────────────────────────────────────
HIVE_PLACEMENT_SPECS: dict[str, dict[str, Any]] = {

    # ── Highest dependency (>= 0.90) ──────────────────────────────────────────

    "almond": {
        "species": "Apis mellifera (primary); Apis cerana (secondary)",
        "hives_per_ha": "6–8",
        "max_forage_m": 300,
        "timing_note": "Place hives 2–3 days before 10% bloom; remove after 80% petal fall.",
        "placement_tip": (
            "Distribute hives in groups of 4–6 at orchard entrances facing south-east. "
            "Provide fresh water within 50 m. Avoid placing near active spray operations."
        ),
    },

    "apple": {
        "species": "Apis mellifera (primary); Apis cerana (secondary for mountain orchards)",
        "hives_per_ha": "4–6",
        "max_forage_m": 250,
        "timing_note": "Introduce at 5–10% bloom (pink-bud stage); move out after last petal falls.",
        "placement_tip": (
            "Place hives on the uphill side of rows so bees forage downward. "
            "In Himachal Pradesh, use native Apis cerana hives for elevations above 2,200 m — "
            "Apis mellifera colonies underperform in cold mountain mornings."
        ),
    },

    "lychee": {
        "species": "Apis cerana (primary); Apis mellifera (secondary)",
        "hives_per_ha": "5–8",
        "max_forage_m": 200,
        "timing_note": "Place 3–5 days before panicle opening; lychee bloom is brief (10–14 days).",
        "placement_tip": (
            "Position hives at the shaded north side of the orchard to prevent overheating "
            "in Bihar's summer heat. Ensure colonies are strong (≥6 combs) before introduction."
        ),
    },

    "cherry": {
        "species": "Apis mellifera (primary); Apis cerana (for temperate hill zones)",
        "hives_per_ha": "4–6",
        "max_forage_m": 200,
        "timing_note": "Introduce at 10–20% bloom; remove after 90% petal fall.",
        "placement_tip": (
            "Cherry requires cross-pollination — ensure at least two compatible cultivars "
            "are present within 100 m of hive placements. Face hives south to maximise "
            "early-morning warm-up."
        ),
    },

    "pear": {
        "species": "Apis mellifera (primary)",
        "hives_per_ha": "3–5",
        "max_forage_m": 250,
        "timing_note": "Place 2–3 days before first bloom; pear often blooms earlier than apple.",
        "placement_tip": (
            "Pear flowers are visited less enthusiastically by bees than apple; use fresh, "
            "vigorous colonies (≥7 combs). Place hives within 150 m of trees to minimise "
            "flight distance in cool spring temperatures."
        ),
    },

    # ── High dependency (0.75–0.90) ───────────────────────────────────────────

    "cardamom": {
        "species": "Apis cerana (essential — enters the tubular cardamom flower)",
        "hives_per_ha": "3–5",
        "max_forage_m": 150,
        "timing_note": "Cardamom blooms staggered April–June in Idukki; introduce colonies at first panicle.",
        "placement_tip": (
            "Apis cerana is the only managed species small enough to enter cardamom flowers. "
            "Place hives in the shade at forest margins. Native-bee colonies kept under forest "
            "canopy near water sources show best fruit set."
        ),
    },

    "mustard": {
        "species": "Apis mellifera (primary); Apis cerana; Apis dorsata (wild, beneficial)",
        "hives_per_ha": "4–6",
        "max_forage_m": 500,
        "timing_note": "Introduce at 10% bloom (mustard blooms 40–50 DAS). Remove before pod fill.",
        "placement_tip": (
            "Mustard is highly attractive to bees; a single colony can service up to 500 m. "
            "Place hives at field corners, 1–2 m above ground on stands, with entrance facing east. "
            "Avoid hive placement within 100 m of active spraying."
        ),
    },

    "saffron": {
        "species": "Apis mellifera; Apis cerana; also native Bombus spp.",
        "hives_per_ha": "4–6",
        "max_forage_m": 300,
        "timing_note": "Saffron blooms October–November; introduce colonies at corm sprouting stage.",
        "placement_tip": (
            "Saffron is a short-season crop (3–4 weeks bloom). Position hives to face away from "
            "prevailing winds in Pampore. Corms are planted densely — bees need clear flight paths "
            "at ≥0.5 m above canopy height."
        ),
    },

    "mango": {
        "species": "Apis cerana (primary for Indian mango); Apis mellifera",
        "hives_per_ha": "3–5",
        "max_forage_m": 400,
        "timing_note": "Introduce 1 week before panicle anthesis (February–March in most zones).",
        "placement_tip": (
            "Mango panicles open over 3–4 weeks — maintain colonies for the full period. "
            "Shade hives from midday sun in Konkan and coastal zones. "
            "Native Apis dorsata nesting nearby provides supplemental pollination at no cost."
        ),
    },

    # ── Moderate-high dependency (0.60–0.75) ──────────────────────────────────

    "sunflower": {
        "species": "Apis mellifera (primary); Apis cerana",
        "hives_per_ha": "3–5",
        "max_forage_m": 600,
        "timing_note": "Introduce at 5–10% bloom. Sunflower is highly self-incompatible — bees essential.",
        "placement_tip": (
            "Distribute hives uniformly — do not cluster at one corner. "
            "One hive per 0.2 ha is the practical spacing for uniform seed set. "
            "In Karnataka, synchronise introduction with the morning peak foraging window (07:00–11:00)."
        ),
    },

    "coffee": {
        "species": "Apis cerana (primary for Coorg arabica); Trigona (stingless bees)",
        "hives_per_ha": "2–4",
        "max_forage_m": 200,
        "timing_note": "Coffee blooms in a burst 1–3 days after the first rains of the season.",
        "placement_tip": (
            "Coffee bloom timing is triggered by rain; have colonies in position 2 weeks early. "
            "Shade-grown coffee under a canopy benefits most from stingless bees (Trigona), "
            "which forage in more confined spaces than Apis cerana."
        ),
    },

    "tea": {
        "species": "Apis cerana (primary for seed crop); Apis mellifera",
        "hives_per_ha": "3–5",
        "max_forage_m": 300,
        "timing_note": "Tea flowers October–December in Assam; for seed crops, introduce at first bud.",
        "placement_tip": (
            "Tea grown for leaf harvest does not need pollination, but seed-crop blocks do. "
            "Position hives on the downhill side of terraces to reduce cold-air drainage stress. "
            "Avoid hive placement near chemical fertiliser storage."
        ),
    },

    "black pepper": {
        "species": "Apis cerana (primary pollinator in Western Ghats)",
        "hives_per_ha": "3–4",
        "max_forage_m": 150,
        "timing_note": "Pepper blooms May–July; introduce colonies at first spike emergence.",
        "placement_tip": (
            "Pepper vines are often grown on supports under shade trees. "
            "Position hives at the base of support trees in the shade. "
            "Apis cerana is preferred over Apis mellifera due to its smaller size and "
            "tolerance of humid forest margins."
        ),
    },

    "cashew": {
        "species": "Apis cerana; Apis mellifera; native halictid bees",
        "hives_per_ha": "3–5",
        "max_forage_m": 300,
        "timing_note": "Cashew blooms January–March in Goa/Konkan. Introduce at 10% bloom.",
        "placement_tip": (
            "Cashew flowers produce both nectar and pollen, making them highly attractive to bees. "
            "Place hives at the windward side of the orchard and ensure each colony has access to "
            "fresh water within 200 m."
        ),
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Stress-level modifiers for urgency framing
# ──────────────────────────────────────────────────────────────────────────────
def _stress_urgency(overall_stress: float) -> str:
    """Return an urgency prefix for the placement advice text."""
    if overall_stress >= 0.65:
        return (
            "URGENT — ecosystem stress is high. Pollination deficit risk is elevated this season. "
            "Deploy managed hives before flowering to compensate for reduced wild pollinator activity."
        )
    if overall_stress >= 0.40:
        return (
            "Moderate stress detected. Supplementary managed hives are recommended to maintain "
            "crop set under current conditions."
        )
    return (
        "Zone conditions are relatively healthy. Managed hives will provide yield insurance "
        "and can increase fruit set beyond baseline levels."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────
def get_hive_placement_advice(
    crops: dict[str, float],
    overall_stress: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Return structured hive-placement recommendations for any crop in *crops*
    with a pollinator dependency >= 0.60 and a known placement spec.

    Parameters
    ----------
    crops : dict[str, float]
        Mapping of crop name (lowercase) → pollinator dependency (0–1).
        Typically comes from ``scores["crop_dependency"]``.
    overall_stress : float
        Zone-level overall stress score (0–1) from the scorer.
        Used to calibrate urgency framing.

    Returns
    -------
    list[dict]
        One entry per qualifying crop, sorted by dependency descending.
        Each entry contains:
            crop, dependency, species, hives_per_ha, max_forage_m,
            timing_note, placement_tip, urgency_note.
        Returns an empty list if no crop meets the threshold or has a spec.
    """
    advice: list[dict[str, Any]] = []
    urgency = _stress_urgency(float(overall_stress))

    for crop, dependency in crops.items():
        dep = float(dependency or 0.0)
        if dep < _DEPENDENCY_THRESHOLD:
            continue
        spec = HIVE_PLACEMENT_SPECS.get(crop.lower())
        if spec is None:
            # Crop qualifies by dependency but has no bespoke spec — emit a
            # generic recommendation so the caller still gets useful output.
            advice.append({
                "crop": crop,
                "dependency": round(dep, 2),
                "species": "Apis cerana or Apis mellifera (contact local KVK for cultivar-specific guidance)",
                "hives_per_ha": "3–5 (generic estimate; consult ICAR Karnal for crop-specific norms)",
                "max_forage_m": 300,
                "timing_note": "Introduce colonies 2–3 days before peak bloom; remove after 80% petal fall.",
                "placement_tip": (
                    "Face entrances south-east for early morning warm-up. "
                    "Ensure fresh water within 100 m. Avoid placement near active pesticide use."
                ),
                "urgency_note": urgency,
            })
            continue

        advice.append({
            "crop": crop,
            "dependency": round(dep, 2),
            "species": spec["species"],
            "hives_per_ha": spec["hives_per_ha"],
            "max_forage_m": spec["max_forage_m"],
            "timing_note": spec["timing_note"],
            "placement_tip": spec["placement_tip"],
            "urgency_note": urgency,
        })

    return sorted(advice, key=lambda row: row["dependency"], reverse=True)
