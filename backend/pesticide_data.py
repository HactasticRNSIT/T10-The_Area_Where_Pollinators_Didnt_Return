import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = ["compute_pesticide_proxy", "validate_pesticide_mappings"]


DATA_DIR = Path(__file__).parent / "data"
PESTICIDE_CSV_PATH = DATA_DIR / "pesticide-use-tonnes.csv"
PESTICIDE_METADATA_PATH = DATA_DIR / "pesticide-use-tonnes.metadata.json"
INDIA_STATE_PESTICIDE_PATH = DATA_DIR / "india-state-pesticides.json"
DEFAULT_COUNTRY_CODE = "IND"


ZONE_COUNTRY_MAP: dict[str, str] = {
    "IN": "IND",
    "FARM_G": "USA", "FARM_H": "USA",
    "BR": "BRA", "CN": "CHN", "FR": "FRA",
    "DE": "DEU", "GB": "GBR", "AU": "AUS",
}

CROP_PESTICIDE_TYPE: dict[str, tuple[str, float]] = {
    "apple": ("neonicotinoid", 1.40),
    "cherry": ("neonicotinoid", 1.40),
    "almonds": ("neonicotinoid", 1.40),
    "canola": ("neonicotinoid", 1.40),
    "stone fruit": ("neonicotinoid", 1.40),
    "cotton": ("organophosphate", 1.20),
    "rice": ("organophosphate", 1.20),
    "orange": ("organophosphate", 1.20),
    "pomegranate": ("organophosphate", 1.20),
    "sunflower": ("pyrethroid", 1.10),
    "mustard": ("pyrethroid", 1.10),
    "wheat": ("pyrethroid", 1.10),
    "soybean": ("pyrethroid", 1.10),
    "mango": ("pyrethroid", 1.10),
    "groundnut": ("pyrethroid", 1.10),
    "sesame": ("pyrethroid", 1.10),
    "maize": ("pyrethroid", 1.10),
    "tomatoes": ("pyrethroid", 1.10),
    "cardamom": ("biopesticide", 0.60),
    "coffee": ("biopesticide", 0.60),
    "black pepper": ("biopesticide", 0.60),
    "rubber": ("biopesticide", 0.60),
    "default": ("pyrethroid", 1.10),
}


def _metadata_impl() -> dict[str, Any]:
    if not PESTICIDE_METADATA_PATH.exists():
        return {}
    try:
        with PESTICIDE_METADATA_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}

_metadata_cache: dict | None = None
_metadata_mtime: float = 0.0

def _metadata() -> dict[str, Any]:
    global _metadata_cache, _metadata_mtime
    mtime = PESTICIDE_METADATA_PATH.stat().st_mtime if PESTICIDE_METADATA_PATH.exists() else 0.0
    if _metadata_cache is None or mtime != _metadata_mtime:
        _metadata_cache = _metadata_impl()
        _metadata_mtime = mtime
    return _metadata_cache


def dataset_citation() -> str:
    columns = _metadata().get("columns", {})
    if isinstance(columns, dict):
        for column in columns.values():
            if isinstance(column, dict) and column.get("citationShort"):
                return str(column["citationShort"])
    return "Food and Agriculture Organization of the United Nations via Our World in Data"


def _load_india_state_pesticide_use_impl() -> dict[str, dict[str, Any]]:
    if not INDIA_STATE_PESTICIDE_PATH.exists():
        return {}
    try:
        with INDIA_STATE_PESTICIDE_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    states = data.get("states", {})
    return states if isinstance(states, dict) else {}

_india_state_cache: dict | None = None
_india_state_mtime: float = 0.0

def load_india_state_pesticide_use() -> dict[str, dict[str, Any]]:
    global _india_state_cache, _india_state_mtime
    mtime = INDIA_STATE_PESTICIDE_PATH.stat().st_mtime if INDIA_STATE_PESTICIDE_PATH.exists() else 0.0
    if _india_state_cache is None or mtime != _india_state_mtime:
        _india_state_cache = _load_india_state_pesticide_use_impl()
        _india_state_mtime = mtime
    return _india_state_cache


def _load_latest_country_pesticide_use_impl() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not PESTICIDE_CSV_PATH.exists():
        return latest

    with PESTICIDE_CSV_PATH.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = (row.get("Code") or "").strip().upper()
            if not code:
                continue
            try:
                year = int(row.get("Year") or "")
                tonnes = float(row.get("Pesticide use") or "")
            except ValueError:
                continue
            current = latest.get(code)
            if current is None or year > int(current["year"]):
                latest[code] = {
                    "entity": (row.get("Entity") or code).strip(),
                    "country_code": code,
                    "year": year,
                    "tonnes": tonnes,
                }
    return latest

_latest_country_cache: dict | None = None
_latest_country_mtime: float = 0.0

def load_latest_country_pesticide_use() -> dict[str, dict[str, Any]]:
    global _latest_country_cache, _latest_country_mtime
    mtime = PESTICIDE_CSV_PATH.stat().st_mtime if PESTICIDE_CSV_PATH.exists() else 0.0
    if _latest_country_cache is None or mtime != _latest_country_mtime:
        _latest_country_cache = _load_latest_country_pesticide_use_impl()
        _latest_country_mtime = mtime
    return _latest_country_cache


def get_latest_country_pesticide_use(country_code: str) -> dict[str, Any] | None:
    return load_latest_country_pesticide_use().get(country_code.upper())


def _zone_prefixes(zone_id: str) -> list[str]:
    if not zone_id:
        return []
    parts = zone_id.split("_")
    return ["_".join(parts[:length]) for length in range(len(parts), 0, -1)]


def country_code_for_zone(zone_id: str) -> str:
    if not zone_id:
        return DEFAULT_COUNTRY_CODE
    for prefix in _zone_prefixes(zone_id):
        if prefix in ZONE_COUNTRY_MAP:
            return ZONE_COUNTRY_MAP[prefix]
    return DEFAULT_COUNTRY_CODE if zone_id.startswith("IN_") else "USA"


def state_demand_for_zone(zone_id: str) -> tuple[str | None, float | None]:
    states = load_india_state_pesticide_use()
    for prefix in _zone_prefixes(zone_id):
        state_data = states.get(prefix)
        if isinstance(state_data, dict):
            value = state_data.get("chemical_demand_mt_2025_26")
            if isinstance(value, (int, float)):
                return prefix, float(value)
    return None, None


def validate_pesticide_mappings(indian_zone_codes: set[str] | None = None) -> list[str]:
    warnings: list[str] = []
    countries = load_latest_country_pesticide_use()

    for prefix, country_code in sorted(ZONE_COUNTRY_MAP.items()):
        if country_code not in countries:
            warnings.append(f"{prefix} maps to missing country code {country_code}")

    if indian_zone_codes:
        states = load_india_state_pesticide_use()
        missing_state_adjustment = sorted(
            code for code in indian_zone_codes
            if code.startswith("IN_") and code not in states
        )
        if missing_state_adjustment:
            joined = ", ".join(missing_state_adjustment)
            warnings.append(f"Indian zone codes without state pesticide adjustment use IND baseline: {joined}")

    return warnings


def _usage_from_demand(demand_mt: float) -> tuple[float, int]:
    usage_ppm = round(max(1.0, min(15.0, demand_mt / 800.0)), 2)
    if usage_ppm < 3.0:
        apps = 1
    elif usage_ppm < 6.0:
        apps = 3
    elif usage_ppm < 10.0:
        apps = 5
    else:
        apps = 7
    return usage_ppm, apps


def compute_pesticide_proxy(zone_id: str, geo_profile: dict | None = None) -> dict[str, Any]:
    from config import get_crop_dependency_for_zone

    warnings: list[str] = []
    country_code = country_code_for_zone(zone_id)
    country = get_latest_country_pesticide_use(country_code)
    if country is None:
        warnings.append(f"OWID/FAO pesticide data missing for {country_code}; using IND baseline")
        country_code = DEFAULT_COUNTRY_CODE
        country = get_latest_country_pesticide_use(country_code)

    if country is None:
        country = {
            "entity": "India",
            "country_code": DEFAULT_COUNTRY_CODE,
            "year": None,
            "tonnes": 40094.0,
        }
        warnings.append("Bundled pesticide dataset unavailable; using conservative embedded India baseline")

    country_tonnes = float(country["tonnes"])
    demand_mt = country_tonnes / 28.0
    state_prefix, state_demand = state_demand_for_zone(zone_id)
    state_data = load_india_state_pesticide_use().get(state_prefix or "", {})
    source_label = "owid_fao_country_baseline_and_crop_model"

    if state_demand is not None:
        demand_mt = state_demand
        source_label = "owid_fao_country_baseline_state_adjusted_and_crop_model"
    elif zone_id.startswith("IN_"):
        warnings.append(f"No state pesticide adjustment for {zone_id}; using India country baseline")

    # We use the geo_profile to get crops if provided. Otherwise fallback to zone default.
    usage_ppm, apps = _usage_from_demand(demand_mt)
    if geo_profile and "crops" in geo_profile:
        crops = geo_profile["crops"]
    else:
        crops = get_crop_dependency_for_zone(zone_id)
    dominant_crop = max(crops, key=crops.get) if crops else "default"
    p_type, toxicity = CROP_PESTICIDE_TYPE.get(dominant_crop, CROP_PESTICIDE_TYPE["default"])

    result = {
        "source": source_label,
        "country_pesticide_tonnes": round(country_tonnes, 2),
        "country_pesticide_year": country.get("year"),
        "country_pesticide_code": country_code,
        "country_pesticide_entity": country.get("entity"),
        "dataset_citation": dataset_citation(),
        "usage_ppm": usage_ppm,
        "applications_per_month": apps,
        "days_since_last_application": 14,
        "pesticide_type": p_type,
        "toxicity_multiplier": toxicity,
        "_fetch_error": None,
    }
    if state_demand is not None:
        result["state_code_reference"] = state_prefix
        result["state_demand_mt_reference"] = round(state_demand, 2)
        if isinstance(state_data, dict):
            result["state_name_reference"] = state_data.get("state_name")
            result["state_bio_demand_mt_reference"] = state_data.get("bio_demand_mt_2025_26")
            result["state_bio_consumption_mt_reference"] = state_data.get("bio_consumption_mt_2024_25")
    if warnings:
        result["_data_warning"] = "; ".join(warnings)
    return result
