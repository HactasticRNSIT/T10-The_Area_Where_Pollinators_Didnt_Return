import os
import sys
import math

sys.path.insert(0, os.path.dirname(__file__))

from config import DEFAULT_CROP_POLLINATION_DEPENDENCY, get_crop_dependency_for_zone
from geo_classifier import _crop_cache, _fetch_groq_crops, clear_crop_cache
from anomaly_detector import _localize_action
from scorer import apply_anomaly_pressure


def test_default_crop_dependency_is_india_oriented():
    crops = get_crop_dependency_for_zone("CUSTOM_ZONE_WITHOUT_PROFILE")

    assert crops == DEFAULT_CROP_POLLINATION_DEPENDENCY
    assert {"mustard", "mango", "rice", "wheat"}.issubset(crops)
    assert "blueberries" not in crops


def test_groq_crop_lookup_caches_missing_api_key(monkeypatch):
    clear_crop_cache()
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    result1 = _fetch_groq_crops(15.4589, 75.0078)
    result2 = _fetch_groq_crops(15.4591, 75.0081)

    assert result1 is None
    assert result2 is None

    # Fix 9.3: assert on key existence rather than total cache size so the test
    # is not fragile to execution order or other tests pre-populating the cache.
    # Both coordinates should round to the same cache key (1 decimal place snap),
    # so exactly one entry was inserted (the negative sentinel for missing API key).
    assert any(
        abs(k[0] - 15.5) < 0.1 and abs(k[1] - 75.0) < 0.1
        for k in _crop_cache
    ), "Expected a cache entry near (15.5, 75.0) after missing-key lookup"


def test_anomaly_pressure_prevents_mild_score_with_many_critical_findings():
    scores = {
        "overall_stress": 0.27,
        "activity_score": 73.0,
        "activity_label": "Moderate",
        "pollination_stress_index": "Medium",
        "crop_risk": {"mustard": "Moderate"},
        "crop_dependency": {"mustard": 0.8},
    }
    anomalies = [
        {"severity": "CRITICAL", "factor": "soil_fertility"},
        {"severity": "CRITICAL", "factor": "climate_variability"},
        {"severity": "CRITICAL", "factor": "pollination_factor"},
    ]
    geo_profile = {"crops": {"mustard": 0.8}}

    adjusted = apply_anomaly_pressure(scores, anomalies, zone_id="IN_RJ_TEST", geo_profile=geo_profile)

    assert adjusted["overall_stress"] >= 0.52
    assert adjusted["activity_label"] == "Stressed"
    assert adjusted["pollination_stress_index"] == "High"
    assert adjusted["anomaly_pressure_adjustment"]["applied"] is True
    assert adjusted["crop_risk"]["mustard"] in {"Moderate", "High", "Severe"}


def test_anomaly_pressure_does_not_inflate_clear_scores_without_critical_findings():
    scores = {
        "overall_stress": 0.62,
        "activity_score": 38.0,
        "activity_label": "Critical",
        "pollination_stress_index": "High",
        "crop_risk": {},
        "crop_dependency": {},
    }

    adjusted = apply_anomaly_pressure(scores, [{"severity": "WARNING", "factor": "soil_fertility"}])

    assert math.isclose(adjusted["overall_stress"], 0.62)
    assert adjusted["anomaly_pressure_adjustment"]["applied"] is False


def test_localize_action_respects_word_boundaries():
    action = "Use borage near field edges, but leave disborage labels unchanged."

    localized = _localize_action(action, "IN_KA_TEST")

    assert "marigold near field edges" in localized
    assert "disborage labels" in localized
