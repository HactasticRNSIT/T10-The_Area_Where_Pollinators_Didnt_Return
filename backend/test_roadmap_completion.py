import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))


def test_crop_risk_legacy_label_and_detail_access(monkeypatch):
    import agmarknet
    monkeypatch.setattr(agmarknet, "get_crop_price_inr", lambda c, s=None: {"price_inr_per_quintal": 1000, "avg_yield_q_per_ha": 10})
    from scorer import compute_crop_risk_details
    from test_support import compute_crop_risks

    risks = compute_crop_risks(0.6, zone_id="IN_HP_01")
    details = compute_crop_risk_details(0.6, zone_id="IN_HP_01")

    assert risks["apple"] in {"Moderate", "High", "Severe"}
    assert "risk_label" in risks["apple"]
    assert risks["apple"].get("risk_label") == details["apple"]["risk_label"]


def test_observation_store_visitation_override(tmp_path):
    from observation_store import record_observation, get_visitation_override

    db_path = str(tmp_path / "obs.db")
    record_observation("IN_KA_TEST", species_name="Apis cerana", pollinator_count=6, db_path=db_path)

    visitation = get_visitation_override("IN_KA_TEST", db_path=db_path)

    assert visitation is not None
    assert visitation["source"] == "field_observation_upload"
    assert visitation["total_observations"] == 1
    assert visitation["avg_visitations_per_hour"] > 0


def test_ibp_merge_replaces_empty_inat():
    from data_fetcher import _merge_visitation_sources

    merged = _merge_visitation_sources(
        {"source": "inat_no_data", "total_observations": 0},
        {"source": "india_biodiversity_portal", "total_observations": 4, "taxon_breakdown": {"apis": 4}},
    )

    assert merged["source"] == "india_biodiversity_portal"
    assert merged["total_observations"] == 4
    assert merged["visitation_ratio"] >= 0


def test_seasonal_threshold_overlay_from_history(tmp_path):
    from history_store import save_run, get_seasonal_threshold_overrides

    db_path = str(tmp_path / "history.db")
    month = datetime.now(timezone.utc).month
    for score in (76, 78, 80):
        save_run(
            "IN_KA_SEASONAL",
            {
                "activity_score": score,
                "overall_stress": 0.2,
                "_meta": {},
                "anomalies": [],
                "analysed_at": datetime(2026, month, 1, tzinfo=timezone.utc).isoformat(),
            },
            db_path=db_path,
        )

    overrides = get_seasonal_threshold_overrides("IN_KA_SEASONAL", month=month, db_path=db_path)

    assert overrides["seasonal_baseline_samples"] == 3
    assert overrides["visitation_ratio_warning"] == 0.82
