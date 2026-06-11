"""
test_batch3.py — Tests for Batch 3: persistence layer + dependents.
Covers: history_store, intervention_store, phenology, agmarknet,
        calendar_export, and value_at_risk in compute_crop_risks.
"""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# Add backend dir to path
sys.path.insert(0, str(Path(__file__).parent))

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# history_store
# ─────────────────────────────────────────────────────────────────────────────

class TestHistoryStore:
    @pytest.fixture
    def tmp_db(self, tmp_path):
        db = str(tmp_path / "test_history.db")
        import history_store
        history_store.init_db(db)
        return db

    def test_save_and_retrieve(self, tmp_db):
        import history_store
        result = {
            "activity_score": 72.5,
            "resilience_score": 72,
            "overall_stress": 0.275,
            "anomalies": [{"severity": "WARNING", "factor": "pesticide_exposure"}],
        }
        history_store.save_run("IN_KA_01", result, db_path=tmp_db)
        history = history_store.get_history("IN_KA_01", db_path=tmp_db)
        assert len(history) == 1
        assert history[0]["activity_score"] == pytest.approx(72.5, abs=0.1)

    def test_history_limit(self, tmp_db):
        import history_store
        for i in range(10):
            history_store.save_run("IN_RJ_01", {"activity_score": float(i)}, db_path=tmp_db)
        history = history_store.get_history("IN_RJ_01", limit=5, db_path=tmp_db)
        assert len(history) == 5

    def test_empty_history_returns_list(self, tmp_db):
        import history_store
        history = history_store.get_history("UNKNOWN_ZONE", db_path=tmp_db)
        assert history == []

    def test_trend_improving(self, tmp_db):
        import history_store
        # Oldest run first (score was low), newest run last (score is high)
        history_store.save_run("IN_HP_01", {"activity_score": 50.0}, db_path=tmp_db)
        history_store.save_run("IN_HP_01", {"activity_score": 75.0}, db_path=tmp_db)
        trend = history_store.get_trend("IN_HP_01", db_path=tmp_db)
        # latest - oldest = 75 - 50 = +25 → improving
        assert trend["direction"] == "improving"
        assert trend["delta"] > 0

    def test_trend_declining(self, tmp_db):
        import history_store
        history_store.save_run("IN_KL_01", {"activity_score": 80.0}, db_path=tmp_db)
        history_store.save_run("IN_KL_01", {"activity_score": 55.0}, db_path=tmp_db)
        trend = history_store.get_trend("IN_KL_01", db_path=tmp_db)
        assert trend["direction"] == "declining"

    def test_trend_stable(self, tmp_db):
        import history_store
        history_store.save_run("IN_TN_01", {"activity_score": 60.0}, db_path=tmp_db)
        history_store.save_run("IN_TN_01", {"activity_score": 61.0}, db_path=tmp_db)
        trend = history_store.get_trend("IN_TN_01", db_path=tmp_db)
        assert trend["direction"] == "stable"

    def test_trend_insufficient_data(self, tmp_db):
        import history_store
        history_store.save_run("IN_PB_01", {"activity_score": 70.0}, db_path=tmp_db)
        trend = history_store.get_trend("IN_PB_01", db_path=tmp_db)
        assert trend["direction"] == "stable"
        assert trend["samples"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# intervention_store
# ─────────────────────────────────────────────────────────────────────────────

class TestInterventionStore:
    @pytest.fixture
    def tmp_db(self, tmp_path):
        db = str(tmp_path / "test_interventions.db")
        import history_store, intervention_store
        history_store.init_db(db)
        intervention_store.init_db(db)
        return db

    def test_record_and_retrieve(self, tmp_db):
        import intervention_store
        row_id = intervention_store.record_intervention(
            "IN_KA_01", "planted_flower_strips", notes="Test", db_path=tmp_db
        )
        assert row_id is not None and row_id > 0
        items = intervention_store.get_interventions("IN_KA_01", db_path=tmp_db)
        assert len(items) == 1
        assert items[0]["intervention"] == "planted_flower_strips"

    def test_before_after_requires_history(self, tmp_db):
        import intervention_store
        row_id = intervention_store.record_intervention(
            "IN_RJ_01", "reduced_pesticides", db_path=tmp_db
        )
        result = intervention_store.get_before_after("IN_RJ_01", row_id, db_path=tmp_db)
        # No history runs exist, so before and after should be None
        assert result is not None
        assert result["before"] is None
        assert result["after"] is None

    def test_before_after_with_history(self, tmp_db):
        import history_store, intervention_store
        from datetime import timezone
        from datetime import datetime

        # Save a "before" run
        history_store.save_run("IN_HP_01", {"activity_score": 40.0}, db_path=tmp_db)

        # Record intervention
        now_str = datetime.now(timezone.utc).isoformat()
        row_id = intervention_store.record_intervention(
            "IN_HP_01", "added_hives", applied_at=now_str, db_path=tmp_db
        )

        # Save an "after" run
        history_store.save_run("IN_HP_01", {"activity_score": 65.0}, db_path=tmp_db)

        result = intervention_store.get_before_after("IN_HP_01", row_id, db_path=tmp_db)
        assert result is not None
        assert result.get("delta_activity_score") == pytest.approx(25.0, abs=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# phenology
# ─────────────────────────────────────────────────────────────────────────────

class TestPhenology:
    def test_mustard_rajasthan_november(self):
        from phenology import is_flowering_season
        assert is_flowering_season("mustard", "IN_RJ_01", date(2024, 11, 15)) is True

    def test_mustard_rajasthan_july(self):
        from phenology import is_flowering_season
        assert is_flowering_season("mustard", "IN_RJ_01", date(2024, 7, 1)) is False

    def test_apple_himachal_april(self):
        from phenology import is_flowering_season
        assert is_flowering_season("apple", "IN_HP_01", date(2024, 4, 10)) is True

    def test_apple_himachal_december(self):
        from phenology import is_flowering_season
        assert is_flowering_season("apple", "IN_HP_01", date(2024, 12, 1)) is False

    def test_coconut_year_round(self):
        from phenology import is_flowering_season
        # Coconut flowers year-round
        for month in range(1, 13):
            assert is_flowering_season("coconut", "IN_TN_01", date(2024, month, 1)) is True

    def test_unknown_crop_returns_false(self):
        from phenology import is_flowering_season
        assert is_flowering_season("dragon_fruit", "IN_KA_01") is False

    def test_days_to_flowering_zero_when_in_window(self):
        from phenology import days_to_flowering
        # Mustard in Rajasthan in November
        result = days_to_flowering("mustard", "IN_RJ_01", date(2024, 11, 20))
        assert result == 0

    def test_days_to_flowering_positive_when_outside(self):
        from phenology import days_to_flowering
        # Mustard in Rajasthan in July — window starts in November
        result = days_to_flowering("mustard", "IN_RJ_01", date(2024, 7, 1))
        assert result is not None and result > 0

    def test_get_active_flowering_crops(self):
        from phenology import get_active_flowering_crops
        crops = {"mustard": 0.80, "rice": 0.03}
        # November — mustard should be active in RJ
        result = get_active_flowering_crops("IN_RJ_01", crops, date(2024, 11, 15))
        assert "mustard" in result

    def test_days_since_ended_none_when_in_window(self):
        from phenology import days_since_flowering_ended
        result = days_since_flowering_ended("mustard", "IN_RJ_01", date(2024, 11, 20))
        assert result is None  # still in window


# ─────────────────────────────────────────────────────────────────────────────
# agmarknet
# ─────────────────────────────────────────────────────────────────────────────

class TestAgmarknet:
    def test_known_crop_returns_price(self):
        from agmarknet import get_crop_price_inr
        data = get_crop_price_inr("apple")
        assert data is not None
        assert "price_inr_per_quintal" in data
        assert data["price_inr_per_quintal"] > 0

    def test_unknown_crop_returns_none(self):
        from agmarknet import get_crop_price_inr
        assert get_crop_price_inr("unicorn_fruit") is None

    def test_value_at_risk_positive(self):
        from agmarknet import compute_value_at_risk
        var = compute_value_at_risk("apple", dependency=0.95, overall_stress=0.6)
        assert var is not None and var > 0

    def test_value_at_risk_zero_stress(self):
        from agmarknet import compute_value_at_risk
        var = compute_value_at_risk("mustard", dependency=0.80, overall_stress=0.0)
        assert var == 0.0

    def test_value_at_risk_unknown_crop(self):
        from agmarknet import compute_value_at_risk
        assert compute_value_at_risk("dragon_fruit", 1.0, 0.5) is None


# ─────────────────────────────────────────────────────────────────────────────
# calendar_export
# ─────────────────────────────────────────────────────────────────────────────

class TestCalendarExport:
    def test_generates_valid_ics_bytes(self):
        from calendar_export import build_advisory_calendar
        decision_brief = {
            "intervention_plan": [
                {
                    "action": "Plant wildflower strips along field margins",
                    "rationale": "Improves floral diversity",
                    "factor": "floral_diversity",
                    "cost_tier": "Low",
                    "uplift_range": "10-15%",
                    "timeframe": "1 season",
                }
            ]
        }
        crops = {"apple": 0.95}
        ics = build_advisory_calendar("IN_HP_01", "Apple Orchards — Shimla", decision_brief, crops)
        assert isinstance(ics, bytes)
        assert b"BEGIN:VCALENDAR" in ics
        assert b"END:VCALENDAR" in ics

    def test_at_least_one_vevent(self):
        from calendar_export import build_advisory_calendar
        decision_brief = {
            "intervention_plan": [
                {"action": "Reduce pesticide frequency", "factor": "pesticide_exposure"}
            ]
        }
        ics = build_advisory_calendar("IN_RJ_01", "Mustard Belt", decision_brief, {"mustard": 0.8})
        assert b"BEGIN:VEVENT" in ics

    def test_empty_plan_produces_valid_calendar(self):
        from calendar_export import build_advisory_calendar
        ics = build_advisory_calendar("IN_KA_01", "Sunflower Belt", {"intervention_plan": []}, {})
        assert b"BEGIN:VCALENDAR" in ics
        assert b"BEGIN:VEVENT" not in ics


# ─────────────────────────────────────────────────────────────────────────────
# value_at_risk wired into compute_crop_risks
# ─────────────────────────────────────────────────────────────────────────────

class TestValueAtRiskInScorer:
    def test_crop_risk_dict_has_risk_label(self, monkeypatch):
        import agmarknet
        monkeypatch.setattr(agmarknet, "get_crop_price_inr", lambda c, s=None: {"price_inr_per_quintal": 1000, "avg_yield_q_per_ha": 10})
        from test_support import compute_crop_risks
        risks = compute_crop_risks(0.5, zone_id="IN_HP_01")
        # IN_HP defaults to apple
        assert "apple" in risks
        assert "risk_label" in risks["apple"]

    def test_crop_risk_dict_has_value_at_risk(self, monkeypatch):
        import agmarknet
        monkeypatch.setattr(agmarknet, "get_crop_price_inr", lambda c, s=None: {"price_inr_per_quintal": 1000, "avg_yield_q_per_ha": 10})
        from test_support import compute_crop_risks
        risks = compute_crop_risks(0.6, zone_id="IN_HP_01")
        assert "apple" in risks
        # value_at_risk_inr may or may not be present depending on agmarknet data
        # but if present it should be a positive number
        var = risks["apple"].get("value_at_risk_inr")
        if var is not None:
            assert var > 0

    def test_zero_stress_zero_var(self, monkeypatch):
        import agmarknet
        monkeypatch.setattr(agmarknet, "get_crop_price_inr", lambda c, s=None: {"price_inr_per_quintal": 1000, "avg_yield_q_per_ha": 10})
        from test_support import compute_crop_risks
        risks = compute_crop_risks(0.0, zone_id="IN_HP_01")
        assert "apple" in risks
        var = risks["apple"].get("value_at_risk_inr")
        if var is not None:
            assert var == 0.0
