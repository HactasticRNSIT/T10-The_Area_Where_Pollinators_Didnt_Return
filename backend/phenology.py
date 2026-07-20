"""
phenology.py — Item 1.3
Crop flowering calendars by zone prefix, sourced from ICAR agro-advisory
bulletins and state KVK data.

month numbering: 1=January, 12=December
Ranges that span year boundaries (e.g., Nov–Feb) are stored as [start, end]
where end < start; `is_flowering_season` handles the wrap.
"""
from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Flowering window registry
# Format: crop → { zone_prefix → [start_month, end_month], ... }
# "IN" is the India-wide fallback used when no more specific prefix matches.
# ---------------------------------------------------------------------------
CROP_FLOWERING_WINDOWS: dict[str, dict[str, list[int]]] = {
    "mustard":   {"IN_RJ": [11, 2], "IN_PB": [10, 1], "IN_UP": [11, 2], "IN": [11, 2]},
    "sunflower": {"IN_KA": [1, 3],  "IN_MH": [12, 2], "IN": [1, 4]},
    "apple":     {"IN_HP": [3, 5],  "IN_JK": [4, 5],  "IN": [3, 5]},
    "mango":     {"IN_UP": [2, 4],  "IN_MH": [1, 3],  "IN": [2, 4]},
    "coffee":    {"IN_KA": [1, 3],  "IN_KL": [1, 3],  "IN": [1, 3]},
    "tea":       {"IN_AS": [3, 5],  "IN": [3, 5]},
    "rice":      {"IN_WB": [8, 10], "IN_PB": [7, 9],  "IN": [7, 10]},
    "cotton":    {"IN_GJ": [6, 8],  "IN_MH": [6, 8],  "IN_TG": [6, 8], "IN": [6, 9]},
    "cardamom":  {"IN_KL": [5, 8],  "IN": [5, 8]},
    "lychee":    {"IN_BR": [2, 4],  "IN_UP": [2, 4],  "IN": [2, 4]},
    "saffron":   {"IN_JK": [10, 11],"IN": [10, 11]},
    "coconut":   {"IN_TN": [1, 12], "IN_KL": [1, 12], "IN": [1, 12]},  # year-round
    "orange":    {"IN_MH": [11, 2], "IN": [11, 2]},
    "sesame":    {"IN_MP": [7, 9],  "IN": [7, 9]},
    "turmeric":  {"IN_TG": [7, 9],  "IN": [7, 9]},
    "wheat":     {"IN_PB": [2, 4],  "IN_UP": [2, 4],  "IN": [2, 4]},
    "bajra":     {"IN_RJ": [8, 10], "IN_GJ": [8, 10], "IN": [8, 10]},
    "groundnut": {"IN_GJ": [7, 10], "IN_AP": [7, 10], "IN_TN": [7, 10], "IN": [7, 10]},
    "jowar":     {"IN_MH": [8, 10], "IN_KA": [8, 10], "IN": [8, 10]},
    "ragi":      {"IN_KA": [8, 10], "IN_TN": [8, 10], "IN": [8, 10]},
    "cumin":     {"IN_RJ": [12, 3], "IN_GJ": [12, 3], "IN": [12, 3]},
    "coriander": {"IN_RJ": [12, 3], "IN_MP": [12, 3], "IN": [12, 3]},
}


def _get_window(crop: str, zone_id: str) -> list[int] | None:
    """Find the best-matching flowering window for a crop/zone pair."""
    windows = CROP_FLOWERING_WINDOWS.get(crop)
    if not windows:
        return None

    # Try increasingly short zone prefixes, then "IN" fallback
    parts = zone_id.split("_")
    for length in range(len(parts), 0, -1):
        prefix = "_".join(parts[:length])
        if prefix in windows:
            return windows[prefix]

    return windows.get("IN")


def _get_windows_for_crops(crops: list[str], zone_id: str) -> dict[str, list[int]]:
    """Return a map of crop to its flowering window for the given zone."""
    result = {}
    for crop in crops:
        window = _get_window(crop, zone_id)
        if window:
            result[crop] = window
    return result

def _in_window(month: int, window: list[int]) -> bool:
    """Return True if month is inside the [start, end] window (handles year wrap)."""
    start, end = window
    if start <= end:
        return start <= month <= end
    else:  # wraps around year boundary (e.g., Nov–Feb)
        return month >= start or month <= end


def is_flowering_season(
    crop: str,
    zone_id: str,
    reference_date: date | datetime | None = None,
) -> bool:
    """Return True if the given date falls within the crop's flowering window."""
    ref = reference_date or date.today()
    if isinstance(ref, datetime):
        ref = ref.date()
    window = _get_window(crop, zone_id)
    if not window:
        return False
    return _in_window(ref.month, window)


def days_to_flowering(
    crop: str,
    zone_id: str,
    reference_date: date | datetime | None = None,
) -> int | None:
    """
    Return the number of days until the crop's flowering window starts.
    Returns 0 if already in the window, None if no window data available.
    """
    ref = reference_date or date.today()
    if isinstance(ref, datetime):
        ref = ref.date()

    window = _get_window(crop, zone_id)
    if not window:
        return None

    if _in_window(ref.month, window):
        return 0

    # Calculate days to start of window
    start_month = window[0]
    # Try this year's start
    try:
        start_this_year = date(ref.year, start_month, 1)
        if start_this_year > ref:
            return (start_this_year - ref).days
        # Next year
        start_next_year = date(ref.year + 1, start_month, 1)
        return (start_next_year - ref).days
    except ValueError:
        return None


def days_since_flowering_ended(
    crop: str,
    zone_id: str,
    reference_date: date | datetime | None = None,
) -> int | None:
    """
    Return the number of days since the crop's flowering window ended.
    Returns None if still in the window or no data available.
    """
    ref = reference_date or date.today()
    if isinstance(ref, datetime):
        ref = ref.date()

    window = _get_window(crop, zone_id)
    if not window:
        return None

    if _in_window(ref.month, window):
        return None  # still flowering

    end_month = window[1]
    try:
        end_this_year = date(ref.year, end_month, 28)  # conservative end-of-month
        if end_this_year < ref:
            return (ref - end_this_year).days
        # Ended last year
        end_last_year = date(ref.year - 1, end_month, 28)
        return (ref - end_last_year).days
    except ValueError:
        return None


def get_active_flowering_crops(
    zone_id: str,
    crop_dependency: dict[str, float],
    reference_date: date | datetime | None = None,
) -> list[str]:
    """Return list of crops (from the zone's crop mix) that are currently flowering."""
    return [
        crop for crop in crop_dependency
        if is_flowering_season(crop, zone_id, reference_date)
    ]
