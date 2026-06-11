"""
test_batch1.py — Comprehensive tests for all Batch 1 / Phase 1 roadmap items.

Covers:
    2.5  Wind speed scoring + anomaly detection
    3.1  Intervention cost-benefit model
    3.4  Hive placement recommendations
    4.3  Structured audit log
    6.2  Inter-factor interaction penalties
    6.3  Confidence interval on activity score
"""

import json
import logging
import math
import pytest
from unittest.mock import patch

from scorer import (
    _linear_stress,
    _clamp,
    score_climate_variability,
    compute_all_scores,
    _interaction_terms,
)
from anomaly_detector import detect_anomalies
from config import (
    ANOMALY_THRESHOLDS,
    SCORING_CONSTANTS,
    INTERACTION_PENALTIES,
    INTERACTION_STRESS_THRESHOLD,
)
from decision_engine import (
    build_decision_brief,
    _data_confidence,
    _cost_benefit,
    _intervention_plan,
)
from hive_placement import (
    get_hive_placement_advice,
    HIVE_PLACEMENT_SPECS,
    _DEPENDENCY_THRESHOLD,
)
from mock_data import get_full_mock_bundle


# ══════════════════════════════════════════════════════════════════════════════
# 2.5 — Wind Speed Scoring + Anomaly Detection
# ══════════════════════════════════════════════════════════════════════════════

class TestWindSpeedScoring:
    """Tests for wind stress integration into score_climate_variability."""

    def test_wind_thresholds_exist_in_config(self):
        """Verify wind thresholds are present and correctly valued."""
        assert "wind_speed_warning" in ANOMALY_THRESHOLDS
        assert "wind_speed_critical" in ANOMALY_THRESHOLDS
        assert ANOMALY_THRESHOLDS["wind_speed_warning"] == 15.0
        assert ANOMALY_THRESHOLDS["wind_speed_critical"] == 25.0

    def test_wind_scoring_constants_exist(self):
        """Verify wind stress ramp constants are present."""
        assert "wind_stress_lo_kmh" in SCORING_CONSTANTS
        assert "wind_stress_hi_kmh" in SCORING_CONSTANTS
        assert SCORING_CONSTANTS["wind_stress_lo_kmh"] == 15.0
        assert SCORING_CONSTANTS["wind_stress_hi_kmh"] == 25.0

    def test_zero_wind_no_stress(self):
        """Wind at 0 km/h should contribute zero stress (below the 15 km/h ramp start)."""
        climate = {
            "temp_std_c": 0.0,
            "total_precipitation_mm": 100.0,
            "precip_std_mm": 0.0,
            "drought_index": 0.0,
            "avg_windspeed_kmh": 0.0,
        }
        stress = score_climate_variability(climate, lat=12.0)
        # With all other inputs at zero stress, wind at 0 → total stress ≈ 0
        assert stress < 0.05, f"Expected near-zero stress, got {stress}"

    def test_moderate_wind_partial_stress(self):
        """Wind at 20 km/h (midpoint of 15–25 ramp) should add partial stress."""
        climate_no_wind = {
            "temp_std_c": 0.0,
            "total_precipitation_mm": 100.0,
            "precip_std_mm": 0.0,
            "drought_index": 0.0,
            "avg_windspeed_kmh": 5.0,  # below ramp
        }
        climate_mid_wind = dict(climate_no_wind)
        climate_mid_wind["avg_windspeed_kmh"] = 20.0  # midpoint of 15–25

        stress_low = score_climate_variability(climate_no_wind, lat=12.0)
        stress_mid = score_climate_variability(climate_mid_wind, lat=12.0)

        assert stress_mid > stress_low, "20 km/h wind should increase climate stress"
        # Wind stress at 20 km/h = linear(20, 15, 25) = 0.5 → contributes 0.5 * 0.15 = 0.075
        expected_delta = 0.5 * 0.15
        actual_delta = stress_mid - stress_low
        assert abs(actual_delta - expected_delta) < 0.02, (
            f"Expected delta ~{expected_delta:.3f}, got {actual_delta:.3f}"
        )

    def test_extreme_wind_full_stress_contribution(self):
        """Wind at 30 km/h (above 25 km/h ceiling) → full wind stress component."""
        climate = {
            "temp_std_c": 0.0,
            "total_precipitation_mm": 100.0,
            "precip_std_mm": 0.0,
            "drought_index": 0.0,
            "avg_windspeed_kmh": 30.0,
        }
        stress = score_climate_variability(climate, lat=12.0)
        # Wind stress = 1.0 * 0.15 = 0.15; all other components near 0
        assert 0.13 <= stress <= 0.18, f"Expected ~0.15 from wind alone, got {stress}"

    def test_none_wind_uses_neutral_stress(self):
        """When avg_windspeed_kmh is None, wind_stress should be _NEUTRAL_STRESS (0.5)."""
        climate_with = {
            "temp_std_c": 0.0,
            "total_precipitation_mm": 100.0,
            "drought_index": 0.0,
            "avg_windspeed_kmh": 5.0,  # below ramp → wind_stress = 0
        }
        climate_without = dict(climate_with)
        climate_without["avg_windspeed_kmh"] = None

        stress_with = score_climate_variability(climate_with, lat=12.0)
        stress_without = score_climate_variability(climate_without, lat=12.0)

        # None → neutral 0.5 → contribution 0.5 * 0.15 = 0.075
        # 5 km/h → 0 stress → contribution 0
        assert stress_without > stress_with, "None wind should use neutral (0.5), not zero"

    def test_wind_stress_monotonicity(self):
        """Wind stress should be monotonically non-decreasing from 0 to 30 km/h."""
        prev_stress = -1.0
        for speed in range(0, 35, 5):
            climate = {
                "temp_std_c": 3.0,
                "total_precipitation_mm": 50.0,
                "drought_index": 0.3,
                "avg_windspeed_kmh": float(speed),
            }
            stress = score_climate_variability(climate, lat=12.0)
            assert stress >= prev_stress - 1e-9, (
                f"Stress decreased from {prev_stress} to {stress} at wind={speed}"
            )
            prev_stress = stress


class TestWindAnomalyDetection:
    """Tests for wind speed anomaly checks in _check_climate."""

    def _make_bundle_with_wind(self, wind_kmh):
        """Build a raw bundle with specific wind speed and otherwise perfect conditions."""
        return {
            "climate": {
                "temp_std_c": 2.0,
                "total_precipitation_mm": 100.0,
                "drought_index": 0.1,
                "avg_windspeed_kmh": wind_kmh,
            },
            "nasa": {"root_zone_wetness": 0.5},
            "gbif": {"species_count": 30},
            "soil": {"ph": 6.5, "organic_carbon_g_per_kg": 3.0, "nitrogen_g_per_kg": 2.0},
            "ndvi": {"ndvi": 0.8, "bare_soil_fraction": 0.1, "disturbance_score": 0.1},
            "pesticide": {"usage_ppm": 0.0, "applications_per_month": 0,
                          "days_since_last_application": 100, "pesticide_type": "biopesticide"},
            "visitation": {
                "source": "inaturalist", "avg_visitations_per_hour": 9.0,
                "expected_visitations_per_hour": 8.5, "visitation_ratio": 1.06,
                "twelve_week_visits_per_hour": [9.0] * 12, "decline_rate_12w": 0.0,
                "pollination_timing_disruption": 0.0, "flowering_success_rate": 0.90,
                "recovery_volatility": 0.0, "total_observations": 42,
                "taxon_breakdown": {"Apis": 28, "Bombus": 14}, "_fetch_error": None,
            },
        }

    def test_no_wind_anomaly_at_10kmh(self):
        """10 km/h is well below warning threshold — no wind anomaly expected."""
        anomalies = detect_anomalies(self._make_bundle_with_wind(10.0))
        wind_anomalies = [a for a in anomalies if a["variable"] == "avg_windspeed_kmh"]
        assert len(wind_anomalies) == 0

    def test_warning_at_15kmh(self):
        """15 km/h is exactly the warning threshold — should trigger WARNING."""
        anomalies = detect_anomalies(self._make_bundle_with_wind(15.0))
        wind_anomalies = [a for a in anomalies if a["variable"] == "avg_windspeed_kmh"]
        assert len(wind_anomalies) == 1
        assert wind_anomalies[0]["severity"] == "WARNING"
        assert wind_anomalies[0]["factor"] == "climate_variability"

    def test_warning_at_20kmh(self):
        """20 km/h is between warning and critical — should be WARNING."""
        anomalies = detect_anomalies(self._make_bundle_with_wind(20.0))
        wind_anomalies = [a for a in anomalies if a["variable"] == "avg_windspeed_kmh"]
        assert len(wind_anomalies) == 1
        assert wind_anomalies[0]["severity"] == "WARNING"

    def test_critical_at_25kmh(self):
        """25 km/h is exactly the critical threshold — should trigger CRITICAL."""
        anomalies = detect_anomalies(self._make_bundle_with_wind(25.0))
        wind_anomalies = [a for a in anomalies if a["variable"] == "avg_windspeed_kmh"]
        assert len(wind_anomalies) == 1
        assert wind_anomalies[0]["severity"] == "CRITICAL"

    def test_critical_at_35kmh(self):
        """35 km/h well above critical — should trigger CRITICAL with correct fields."""
        anomalies = detect_anomalies(self._make_bundle_with_wind(35.0))
        wind_anomalies = [a for a in anomalies if a["variable"] == "avg_windspeed_kmh"]
        assert len(wind_anomalies) == 1
        a = wind_anomalies[0]
        assert a["severity"] == "CRITICAL"
        assert a["observed_value"] == 35.0
        assert a["threshold"] == 25.0
        assert "foraging ceases" in a["description"].lower()
        assert len(a["recommended_action"]) > 0

    def test_no_wind_anomaly_when_none(self):
        """When avg_windspeed_kmh is None, no wind anomaly should fire."""
        anomalies = detect_anomalies(self._make_bundle_with_wind(None))
        wind_anomalies = [a for a in anomalies if a["variable"] == "avg_windspeed_kmh"]
        assert len(wind_anomalies) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 3.1 — Intervention Cost-Benefit Model
# ══════════════════════════════════════════════════════════════════════════════

class TestCostBenefit:
    """Tests for the intervention cost-benefit keyword matcher."""

    def test_irrigation_keyword_matches(self):
        result = _cost_benefit("Install supplementary water stations (shallow dishes with pebbles)")
        assert result["cost_tier"] == "Low"
        assert result["timeframe"] == "Immediate"

    def test_ipm_keyword_matches(self):
        result = _cost_benefit(
            "Adopt an Integrated Pest Management (IPM) protocol limiting applications..."
        )
        assert result["cost_tier"] == "Medium"
        assert "20" in result["uplift_range"]  # "20–40%"

    def test_wildflower_strip_matches(self):
        result = _cost_benefit("Oversow 2–3 m wide wildflower strips along all field boundaries")
        assert result["cost_tier"] == "Low"
        assert result["timeframe"] == "1 season"

    def test_hive_matches_high_cost(self):
        result = _cost_benefit("Relocate hives to the most sheltered corner of the zone")
        # "relocate hive" (longer) should match before bare "hive"
        assert result["cost_tier"] == "Medium"
        assert result["timeframe"] == "Immediate"

    def test_neem_oil_matches(self):
        result = _cost_benefit("Switch to neem oil (Azadirachtin) or kaolin clay sprays")
        assert result["cost_tier"] == "Low"
        assert "15" in result["uplift_range"]

    def test_fallback_for_unknown_action(self):
        result = _cost_benefit("Consult your local astrologer for cosmic advice")
        assert result["cost_tier"] == "Medium"
        assert result["uplift_range"] == "10–20%"
        assert result["timeframe"] == "1–2 seasons"

    def test_longest_keyword_wins(self):
        """'drip irrigation' should match before 'irrigation'."""
        result = _cost_benefit("Activate drip irrigation at field margins at 3–4 mm/day")
        assert result["cost_tier"] == "Medium"

    def test_case_insensitive(self):
        result = _cost_benefit("Apply MULCH (straw or wood chip, 5 cm depth)")
        assert result["cost_tier"] == "Low"

    def test_cost_fields_in_intervention_plan(self):
        """Verify that _intervention_plan items carry the cost-benefit fields."""
        anomalies = [{
            "factor": "climate_variability",
            "variable": "total_precipitation_mm",
            "severity": "CRITICAL",
            "observed_value": 5.0,
            "threshold": 10.0,
            "description": "Only 5 mm of rainfall in 30 days.",
            "recommended_action": (
                "Install supplementary water stations (shallow dishes with pebbles) "
                "at 50 m intervals across the zone."
            ),
        }]
        factor_scores = {"climate_variability": 0.8}
        weights = {"climate_variability": 0.25}
        plan = _intervention_plan(anomalies, factor_scores, weights)

        assert len(plan) == 1
        item = plan[0]
        assert "cost_tier" in item
        assert "uplift_range" in item
        assert "timeframe" in item
        assert item["cost_tier"] == "Low"
        assert item["timeframe"] == "Immediate"


# ══════════════════════════════════════════════════════════════════════════════
# 3.4 — Hive Placement Recommendations
# ══════════════════════════════════════════════════════════════════════════════

class TestHivePlacement:
    """Tests for the hive placement advisory module."""

    def test_high_dependency_crops_get_advice(self):
        """Apple (0.95) should return placement advice."""
        advice = get_hive_placement_advice({"apple": 0.95})
        assert len(advice) == 1
        item = advice[0]
        assert item["crop"] == "apple"
        assert item["dependency"] == 0.95
        assert "Apis" in item["species"]
        assert item["max_forage_m"] > 0
        assert len(item["timing_note"]) > 0
        assert len(item["placement_tip"]) > 0

    def test_low_dependency_crops_excluded(self):
        """Wheat at 0.10 is well below 0.60 threshold — no advice."""
        advice = get_hive_placement_advice({"wheat": 0.10})
        assert len(advice) == 0

    def test_threshold_boundary(self):
        """Crops at exactly 0.60 should qualify."""
        advice = get_hive_placement_advice({"cardamom": 0.60})
        assert len(advice) == 1

    def test_below_threshold_excluded(self):
        """Crops at 0.59 should not qualify."""
        advice = get_hive_placement_advice({"unknown_crop": 0.59})
        assert len(advice) == 0

    def test_multiple_crops_sorted_by_dependency(self):
        """Multiple qualifying crops should be sorted descending by dependency."""
        crops = {"apple": 0.95, "mustard": 0.80, "sunflower": 0.65}
        advice = get_hive_placement_advice(crops)
        assert len(advice) == 3
        assert advice[0]["dependency"] >= advice[1]["dependency"]
        assert advice[1]["dependency"] >= advice[2]["dependency"]

    def test_unknown_crop_gets_generic_advice(self):
        """A high-dependency crop not in HIVE_PLACEMENT_SPECS gets generic advice."""
        advice = get_hive_placement_advice({"passion_fruit": 0.85})
        assert len(advice) == 1
        item = advice[0]
        assert "generic" in item["hives_per_ha"].lower() or "KVK" in item["species"]
        assert item["max_forage_m"] == 300  # generic default

    def test_stress_urgency_framing_high(self):
        """High stress (≥0.65) should produce URGENT urgency note."""
        advice = get_hive_placement_advice({"apple": 0.95}, overall_stress=0.70)
        assert "URGENT" in advice[0]["urgency_note"].upper()

    def test_stress_urgency_framing_moderate(self):
        """Moderate stress (0.40–0.65) should produce moderate urgency."""
        advice = get_hive_placement_advice({"apple": 0.95}, overall_stress=0.50)
        assert "moderate" in advice[0]["urgency_note"].lower()

    def test_stress_urgency_framing_healthy(self):
        """Low stress (<0.40) should produce healthy urgency note."""
        advice = get_hive_placement_advice({"apple": 0.95}, overall_stress=0.20)
        assert "healthy" in advice[0]["urgency_note"].lower()

    def test_empty_crops_returns_empty(self):
        """Empty crop dict should return empty list."""
        assert get_hive_placement_advice({}) == []

    def test_all_spec_crops_have_required_fields(self):
        """Every entry in HIVE_PLACEMENT_SPECS should have all required fields."""
        required = {"species", "hives_per_ha", "max_forage_m", "timing_note", "placement_tip"}
        for crop, spec in HIVE_PLACEMENT_SPECS.items():
            missing = required - set(spec.keys())
            assert not missing, f"Crop '{crop}' missing fields: {missing}"

    def test_hive_placement_wired_into_decision_brief(self):
        """build_decision_brief should include hive_placement key."""
        raw = get_full_mock_bundle(12.97, 77.59)
        scores = compute_all_scores(raw, zone_id="IN_KA")
        brief = build_decision_brief(scores, [], raw)
        assert "hive_placement" in brief
        assert isinstance(brief["hive_placement"], list)


# ══════════════════════════════════════════════════════════════════════════════
# 4.3 — Structured Audit Log
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditLog:
    """Tests for the structured audit log emitted by analyse_zone."""

    def test_audit_log_emitted_at_info_level(self):
        """analyse_zone should emit an INFO log record with an 'audit' extra dict."""
        from main import analyse_zone

        captured_records = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                if hasattr(record, "audit"):
                    captured_records.append(record)

        handler = CaptureHandler()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("main")
        original_level = logger.level
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            analyse_zone("IN_KA_01", 12.97, 77.59)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(original_level)

        assert len(captured_records) >= 1, "Expected at least one audit log record"
        record = captured_records[0]
        audit = record.audit
        assert isinstance(audit, dict)
        assert audit["zone_id"] == "IN_KA_01"
        assert abs(audit["lat"] - 12.97) < 0.01
        assert abs(audit["lon"] - 77.59) < 0.01
        assert audit["duration_ms"] >= 0
        assert isinstance(audit["activity_score"], (int, float))
        assert isinstance(audit["overall_stress"], float)
        assert isinstance(audit["anomaly_count"], int)
        assert isinstance(audit["critical_count"], int)
        assert isinstance(audit["warning_count"], int)
        assert isinstance(audit["groq_called"], bool)
        assert "decision_grade" in audit

    def test_audit_log_json_serialisable(self):
        """The audit dict should be JSON-serialisable (no datetime, no set, etc.)."""
        from main import analyse_zone

        captured_audit = {}

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                if hasattr(record, "audit"):
                    captured_audit.update(record.audit)

        handler = CaptureHandler()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("main")
        original_level = logger.level
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            analyse_zone("IN_KA_01", 12.97, 77.59)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(original_level)

        # Should not raise
        serialised = json.dumps(captured_audit)
        assert isinstance(serialised, str)
        assert len(serialised) > 10


# ══════════════════════════════════════════════════════════════════════════════
# 6.2 — Inter-factor Interaction Penalties
# ══════════════════════════════════════════════════════════════════════════════

class TestInteractionPenalties:
    """Tests for synergistic inter-factor interaction terms."""

    def test_no_penalty_when_all_low(self):
        """No penalty when all factor stresses are below the activation threshold."""
        factor_scores = {
            "pesticide_exposure": 0.30,
            "floral_diversity": 0.40,
            "nesting_availability": 0.20,
            "soil_fertility": 0.30,
        }
        assert _interaction_terms(factor_scores) == 0.0

    def test_no_penalty_when_only_one_factor_high(self):
        """Penalty requires BOTH factors above threshold — one high is not enough."""
        factor_scores = {
            "pesticide_exposure": 0.90,
            "floral_diversity": 0.30,  # below threshold
            "nesting_availability": 0.20,
            "soil_fertility": 0.10,
        }
        assert _interaction_terms(factor_scores) == 0.0

    def test_single_pair_activates(self):
        """pesticide + floral both above 0.70 → 0.08 penalty."""
        factor_scores = {
            "pesticide_exposure": 0.80,
            "floral_diversity": 0.75,
            "nesting_availability": 0.20,
            "soil_fertility": 0.10,
        }
        penalty = _interaction_terms(factor_scores)
        assert math.isclose(penalty, 0.08, abs_tol=1e-9)

    def test_two_pairs_activate(self):
        """pesticide + floral (0.08) AND pesticide + nesting (0.05) → 0.13."""
        factor_scores = {
            "pesticide_exposure": 0.85,
            "floral_diversity": 0.80,
            "nesting_availability": 0.75,
            "soil_fertility": 0.10,
        }
        penalty = _interaction_terms(factor_scores)
        assert math.isclose(penalty, 0.13, abs_tol=1e-9)

    def test_all_three_pairs_activate(self):
        """All three pairs → 0.08 + 0.05 + 0.04 = 0.17."""
        factor_scores = {
            "pesticide_exposure": 0.80,
            "floral_diversity": 0.80,
            "nesting_availability": 0.80,
            "soil_fertility": 0.80,
        }
        penalty = _interaction_terms(factor_scores)
        assert math.isclose(penalty, 0.17, abs_tol=1e-9)

    def test_exactly_at_threshold_activates(self):
        """Factors at exactly INTERACTION_STRESS_THRESHOLD (0.70) should activate."""
        factor_scores = {
            "pesticide_exposure": 0.70,
            "floral_diversity": 0.70,
        }
        penalty = _interaction_terms(factor_scores)
        assert penalty == 0.08

    def test_just_below_threshold_does_not_activate(self):
        """Factors at 0.699 should NOT activate."""
        factor_scores = {
            "pesticide_exposure": 0.699,
            "floral_diversity": 0.70,
        }
        penalty = _interaction_terms(factor_scores)
        assert penalty == 0.0

    def test_interaction_penalty_in_compute_all_scores(self):
        """compute_all_scores should include interaction_penalty in factor_scores."""
        raw = get_full_mock_bundle(12.97, 77.59)
        scores = compute_all_scores(raw, zone_id="IN_KA")
        assert "interaction_penalty" in scores["factor_scores"]
        assert isinstance(scores["factor_scores"]["interaction_penalty"], float)

    def test_interaction_penalty_does_not_break_bounds(self):
        """Overall stress must remain in [0, 1] even with maximum penalty."""
        raw = get_full_mock_bundle(12.97, 77.59)
        # Force very high stress on all factors
        raw["pesticide"] = {
            "usage_ppm": 50.0, "applications_per_month": 10,
            "days_since_last_application": 0, "pesticide_type": "neonicotinoid",
            "toxicity_multiplier": 2.0,
        }
        raw["ndvi"] = {"ndvi": 0.05, "bare_soil_fraction": 0.9, "disturbance_score": 0.95}
        raw["soil"] = {"ph": 9.0, "organic_carbon_g_per_kg": 0.1, "nitrogen_g_per_kg": 0.05}
        raw["climate"] = {
            "temp_std_c": 15.0, "total_precipitation_mm": 0.0,
            "drought_index": 1.0, "avg_windspeed_kmh": 35.0,
        }
        scores = compute_all_scores(raw, zone_id="IN_KA")
        assert 0.0 <= scores["overall_stress"] <= 1.0

    def test_config_values_match_documentation(self):
        """Verify the documented interaction penalty values and threshold."""
        assert INTERACTION_PENALTIES[("pesticide_exposure", "floral_diversity")] == 0.08
        assert INTERACTION_PENALTIES[("pesticide_exposure", "nesting_availability")] == 0.05
        assert INTERACTION_PENALTIES[("soil_fertility", "floral_diversity")] == 0.04
        assert INTERACTION_STRESS_THRESHOLD == 0.70


# ══════════════════════════════════════════════════════════════════════════════
# 6.3 — Confidence Interval on Activity Score
# ══════════════════════════════════════════════════════════════════════════════

class TestConfidenceInterval:
    """Tests for the data-quality-driven confidence margin on activity score."""

    def test_high_confidence_tight_margin(self):
        """All-live sources → High confidence, margin = 3."""
        source_health = {
            "climate": {"source": "open_meteo", "quality": "live"},
            "soil":    {"source": "isric_soilgrids", "quality": "live"},
            "ndvi":    {"source": "eosda_satellite", "quality": "live"},
        }
        conf = _data_confidence(source_health)
        assert conf["label"] == "High"
        assert conf["margin"] == 3

    def test_medium_confidence_moderate_margin(self):
        """Mixed live/modelled → Medium confidence, margin = 8."""
        # 1 live + 3 modelled = (1.0 + 0.72 + 0.72 + 0.72) / 4 = 0.79 → 79% → Medium
        source_health = {
            "climate":    {"source": "open_meteo", "quality": "live"},
            "soil":       {"source": "isric_soilgrids", "quality": "modelled"},
            "ndvi":       {"source": "modelled_ndvi", "quality": "modelled"},
            "visitation": {"source": "model", "quality": "modelled"},
        }
        conf = _data_confidence(source_health)
        assert conf["label"] == "Medium"
        assert conf["margin"] == 8

    def test_limited_confidence_wide_margin(self):
        """All-fallback sources → Limited confidence, margin = 15."""
        source_health = {
            "climate":   {"source": "mock", "quality": "fallback"},
            "soil":      {"source": "mock", "quality": "fallback"},
            "ndvi":      {"source": "mock", "quality": "fallback"},
        }
        conf = _data_confidence(source_health)
        assert conf["label"] == "Limited"
        assert conf["margin"] == 15

    def test_empty_source_health_defaults(self):
        """No source_health → Limited, score 50, margin 15."""
        conf = _data_confidence({})
        assert conf["score"] == 50
        assert conf["label"] == "Limited"
        assert conf["margin"] == 15

    def test_margin_propagates_to_decision_brief(self):
        """build_decision_brief should expose activity_score_margin and activity_score_range."""
        raw = get_full_mock_bundle(12.97, 77.59)
        scores = compute_all_scores(raw, zone_id="IN_KA")
        brief = build_decision_brief(scores, [], raw)

        assert "activity_score_margin" in brief
        assert "activity_score_range" in brief
        assert isinstance(brief["activity_score_margin"], int)
        lo, hi = brief["activity_score_range"]
        assert lo <= hi
        assert lo >= 0.0
        assert hi <= 100.0

    def test_range_clamps_at_boundaries(self):
        """Activity score near 0 or 100 should not produce out-of-range intervals."""
        # Simulate activity_score near 100 with Limited confidence (margin 15)
        scores = {
            "activity_score": 98.0,
            "overall_stress": 0.02,
            "factor_scores": {},
            "factor_weights": {},
            "crop_dependency": {},
        }
        raw = {"_realtime": {"source_health": {}}}  # no source → Limited → margin 15
        brief = build_decision_brief(scores, [], raw)
        lo, hi = brief["activity_score_range"]
        assert hi <= 100.0, f"Upper bound exceeded 100: {hi}"
        assert lo >= 0.0

    def test_range_width_equals_double_margin(self):
        """Range width should be 2 × margin (or clipped at bounds)."""
        scores = {
            "activity_score": 60.0,
            "overall_stress": 0.40,
            "factor_scores": {},
            "factor_weights": {},
            "crop_dependency": {},
        }
        # All live → High → margin 3
        raw = {
            "_realtime": {"source_health": {
                "a": {"quality": "live"}, "b": {"quality": "live"}, "c": {"quality": "live"},
            }}
        }
        brief = build_decision_brief(scores, [], raw)
        lo, hi = brief["activity_score_range"]
        assert math.isclose(hi - lo, 2 * 3, abs_tol=0.2)


# ══════════════════════════════════════════════════════════════════════════════
# Integration: all Batch 1 features flow through compute_all_scores + brief
# ══════════════════════════════════════════════════════════════════════════════

class TestBatch1Integration:
    """End-to-end integration tests verifying Batch 1 features work together."""

    def test_full_pipeline_with_wind_and_interactions(self):
        """Run the full scorer + decision engine pipeline and verify new fields are present."""
        raw = get_full_mock_bundle(12.97, 77.59)
        raw["climate"]["avg_windspeed_kmh"] = 20.0  # add wind data

        scores = compute_all_scores(raw, zone_id="IN_KA")
        anomalies = detect_anomalies(raw, zone_id="IN_KA")
        brief = build_decision_brief(scores, anomalies, raw)

        # 2.5: wind data should have influenced the climate score
        assert scores["factor_scores"]["climate_variability"] is not None

        # 6.2: interaction_penalty should be present
        assert "interaction_penalty" in scores["factor_scores"]

        # 3.4: hive_placement should be present
        assert "hive_placement" in brief

        # 6.3: confidence interval
        assert "activity_score_margin" in brief
        assert "activity_score_range" in brief

        # 3.1: if anomalies produced an intervention plan, cost fields should exist
        if brief["intervention_plan"]:
            item = brief["intervention_plan"][0]
            assert "cost_tier" in item
            assert "uplift_range" in item
            assert "timeframe" in item

    def test_wind_anomaly_triggers_cost_benefit_in_plan(self):
        """A critical wind anomaly should produce an intervention with cost-benefit fields."""
        raw = get_full_mock_bundle(12.97, 77.59)
        raw["climate"]["avg_windspeed_kmh"] = 30.0  # trigger CRITICAL

        scores = compute_all_scores(raw, zone_id="IN_KA")
        anomalies = detect_anomalies(raw, zone_id="IN_KA")
        brief = build_decision_brief(scores, anomalies, raw)

        # Find the wind anomaly in the intervention plan
        wind_items = [
            item for item in brief["intervention_plan"]
            if item["variable"] == "avg_windspeed_kmh"
        ]
        if wind_items:
            item = wind_items[0]
            assert item["severity"] == "CRITICAL"
            assert "cost_tier" in item
            assert "uplift_range" in item
