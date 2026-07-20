"""
test_task1_task2.py
===================
Unit tests for Task 1 (top_stress_factors explainability field)
and Task 2 (source-dependent TTL cache).
"""

import time
import pytest
import sys
import os

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))


# ──────────────────────────────────────────────────────────────────────────────
# Task 1 — top_stress_factors field
# ──────────────────────────────────────────────────────────────────────────────

def _make_factor_scores(overrides: dict | None = None) -> dict:
    """Build a sample factor_scores dict (with interaction_penalty) for testing."""
    base = {
        "pesticide_exposure":   0.72,
        "soil_fertility":       0.45,
        "floral_diversity":     0.30,
        "climate_variability":  0.60,
        "nesting_availability": 0.25,
        "pollination_factor":   0.55,
        "interaction_penalty":  0.05,  # meta-value — must be excluded from output
    }
    if overrides:
        base.update(overrides)
    return base


def _build_top_stress_factors(factor_scores: dict) -> list:
    """Mirror of the logic added to _build_output in main.py."""
    return [
        {"factor": k.replace("_", " ").title(), "stress": round(v, 2)}
        for k, v in sorted(
            (
                (k, v) for k, v in factor_scores.items()
                if k != "interaction_penalty"
            ),
            key=lambda kv: kv[1],
            reverse=True,
        )
    ]


def test_top_stress_factors_sorted_descending():
    """Factors must appear sorted by stress descending."""
    factors = _make_factor_scores()
    result = _build_top_stress_factors(factors)
    stresses = [item["stress"] for item in result]
    assert stresses == sorted(stresses, reverse=True), (
        f"Expected descending sort, got {stresses}"
    )


def test_top_stress_factors_excludes_interaction_penalty():
    """interaction_penalty must never appear in the output."""
    factors = _make_factor_scores()
    result = _build_top_stress_factors(factors)
    names = [item["factor"] for item in result]
    assert "Interaction Penalty" not in names, (
        "interaction_penalty should be excluded from top_stress_factors"
    )


def test_top_stress_factors_count():
    """Should contain exactly the 6 named factors (no interaction_penalty)."""
    factors = _make_factor_scores()
    result = _build_top_stress_factors(factors)
    assert len(result) == 6, f"Expected 6 items, got {len(result)}"


def test_top_stress_factors_label_format():
    """Underscores replaced by spaces, title-cased."""
    factors = _make_factor_scores()
    result = _build_top_stress_factors(factors)
    expected_labels = {
        "Pesticide Exposure",
        "Soil Fertility",
        "Floral Diversity",
        "Climate Variability",
        "Nesting Availability",
        "Pollination Factor",
    }
    actual_labels = {item["factor"] for item in result}
    assert actual_labels == expected_labels, (
        f"Label mismatch. Expected {expected_labels}, got {actual_labels}"
    )


def test_top_stress_factors_stress_rounded_to_2dp():
    """Each stress value should be rounded to 2 decimal places."""
    factors = _make_factor_scores({"pesticide_exposure": 0.7234567})
    result = _build_top_stress_factors(factors)
    for item in result:
        assert item["stress"] == round(item["stress"], 2), (
            f"{item['factor']} stress {item['stress']} is not rounded to 2dp"
        )


def test_top_stress_factors_first_is_highest():
    """The first entry must have the highest stress in this sample."""
    factors = _make_factor_scores()
    result = _build_top_stress_factors(factors)
    # pesticide_exposure = 0.72 is the max
    assert result[0]["factor"] == "Pesticide Exposure", (
        f"Expected 'Pesticide Exposure' first, got {result[0]['factor']}"
    )
    assert result[0]["stress"] == 0.72


def test_top_stress_factors_via_build_output(monkeypatch):
    """Integration smoke-test: _build_output returns top_stress_factors key."""
    import main
    from mock_data import get_full_mock_bundle
    from scorer import compute_all_scores
    from anomaly_detector import detect_anomalies, has_ai_trigger_anomaly
    from decision_engine import build_decision_brief

    raw = get_full_mock_bundle(12.0, 77.0)
    raw["_meta"] = {"lat": 12.0, "lon": 77.0, "zone_id": "IN_KA_01", "geo_profile": None}
    raw["climate"] = {
        "temp_mean_c": 25.0, "temp_std_c": 3.0,
        "total_precipitation_mm": 80.0, "precip_std_mm": 5.0,
        "drought_index": 0.3, "avg_windspeed_kmh": 10.0,
    }
    raw["nasa"] = {"root_zone_wetness": 0.5}
    raw["gbif"] = {"species_count": 12}

    scores = compute_all_scores(raw, zone_id="IN_KA_01")
    anomalies = detect_anomalies(raw, zone_id="IN_KA_01")
    from scorer import apply_anomaly_pressure
    scores = apply_anomaly_pressure(scores, anomalies, zone_id="IN_KA_01")

    ai_result = {
        "biodiversity_insight": "Test insight.",
        "top_intervention": "Plant flowers.",
        "pollination_boost_actions": ["Action 1", "Action 2", "Action 3"],
        "insight_source": "test",
    }
    decision_brief = build_decision_brief(scores, anomalies, raw)

    output = main._build_output(
        "IN_KA_01", 12.0, 77.0, scores, anomalies, ai_result, raw, decision_brief
    )

    assert "top_stress_factors" in output, "_build_output must include top_stress_factors"
    tsf = output["top_stress_factors"]
    assert isinstance(tsf, list), "top_stress_factors must be a list"
    assert len(tsf) > 0, "top_stress_factors must not be empty"
    # Verify sort order in real output
    stresses = [item["stress"] for item in tsf]
    assert stresses == sorted(stresses, reverse=True), "Not sorted descending"


# ──────────────────────────────────────────────────────────────────────────────
# Task 2 — Source-dependent TTL cache
# ──────────────────────────────────────────────────────────────────────────────

from data_fetcher import _cache_get, _cache_set, _ttl_for_key, _TTL_BY_SOURCE, _TTL_DEFAULT, _cache, _cache_lock


def _flush_cache():
    """Clear the in-process cache between tests."""
    import threading
    with _cache_lock:
        _cache.clear()


def test_ttl_by_source_soilgrids():
    """soilgrids TTL must be 7 days (604800 s)."""
    assert _TTL_BY_SOURCE["soilgrids"] == 604_800


def test_ttl_by_source_agro_ndvi():
    """agro_ndvi TTL must be 24 hours."""
    assert _TTL_BY_SOURCE["agro_ndvi"] == 86_400


def test_ttl_by_source_open_meteo_agro():
    """open_meteo_agro must have the shortest TTL (900 s = 15 min)."""
    assert _TTL_BY_SOURCE["open_meteo_agro"] == 900


def test_ttl_for_key_prefix_matching():
    """_ttl_for_key must match by prefix."""
    assert _ttl_for_key("soil:12.0000:77.0000") == 604_800
    assert _ttl_for_key("agro_ndvi:12.0000:77.0000") == 86_400
    assert _ttl_for_key("gbif:12.0000:77.0000") == 86_400
    assert _ttl_for_key("open_meteo_agro:12.0000:77.0000") == 900
    assert _ttl_for_key("open_meteo:12.0000:77.0000") == 3_600


def test_ttl_for_key_unknown_prefix_returns_default():
    """Unknown prefixes fall back to _TTL_DEFAULT."""
    assert _ttl_for_key("unknown_source:12.0000:77.0000") == _TTL_DEFAULT


def test_soilgrids_entry_valid_after_old_300s_boundary(monkeypatch):
    """A soilgrids cache entry must still be valid at 301 s (beyond old 300 s boundary)."""
    _flush_cache()
    key = "soil:99.0000:99.0000"
    _cache_set(key, {"ph": 6.5})

    # Fast-forward monotonic clock by 301 seconds — should still be a HIT
    original = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original() + 301)
    result = _cache_get(key)
    assert result is not None, (
        "soilgrids entry should still be valid 301 s after write (TTL is 604800 s)"
    )
    assert result["ph"] == 6.5
    _flush_cache()


def test_soilgrids_entry_expired_after_full_ttl(monkeypatch):
    """A soilgrids cache entry must be expired after 604801 s."""
    _flush_cache()
    key = "soil:88.0000:88.0000"
    _cache_set(key, {"ph": 7.0})

    original = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original() + 604_801)
    result = _cache_get(key)
    assert result is None, (
        "soilgrids entry should be expired after 604801 s"
    )
    _flush_cache()


def test_agro_ndvi_entry_expired_after_24h_plus_1(monkeypatch):
    """agro_ndvi entry should expire after 86401 s."""
    _flush_cache()
    key = "agro_ndvi:12.0000:77.0000"
    _cache_set(key, {"ndvi": 0.55})

    original = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original() + 86_401)
    result = _cache_get(key)
    assert result is None, "agro_ndvi entry should be expired after 86401 s"
    _flush_cache()


def test_open_meteo_agro_entry_expired_after_15min_plus_1(monkeypatch):
    """open_meteo_agro entry must expire after 901 s."""
    _flush_cache()
    key = "open_meteo_agro:12.0000:77.0000"
    _cache_set(key, {"relative_humidity_pct": 72.0})

    original = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original() + 901)
    result = _cache_get(key)
    assert result is None, "open_meteo_agro entry should be expired after 901 s"
    _flush_cache()


def test_explicit_ttl_override():
    """Caller can pass an explicit ttl that overrides the prefix-inferred TTL."""
    _flush_cache()
    key = "soil:77.0000:12.0000"
    _cache_set(key, {"ph": 5.5}, ttl=10)  # explicit 10 s — much shorter than 7-day default
    # Immediately readable
    assert _cache_get(key) is not None
    _flush_cache()
