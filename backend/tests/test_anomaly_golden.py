"""
tests/test_anomaly_golden.py
────────────────────────────────────────────────────────────────────────────
Golden-dataset regression tests for `anomaly_detector.detect_anomalies`.

Each fixture in tests/golden/*.json describes:
  • "zone_id"  — passed to detect_anomalies
  • "raw"      — the full raw-data bundle
  • "expected" — assertions to make on the returned anomaly list:
      anomaly_count        : exact count (int), OR
      anomaly_count_min    : minimum count (int)
      must_include         : list of {factor, severity, variable} dicts that
                             must each match at least one returned anomaly
      no_india_terms       : list of strings that must NOT appear in any
                             recommended_action when zone is IN_*
      india_terms_required : list of strings where at least one must appear
                             across all recommended_actions (localisation check)
      india_terms_must_not_appear : terms that must be absent (EU fixture)
      uk_terms_required    : UK terms that must be present for non-IN_ zones

How to run:
    pytest tests/test_anomaly_golden.py -v
"""

import json
import sys
import pathlib

import pytest

# ── path surgery so the test can be run from the repo root or from tests/ ─────
_BACKEND = pathlib.Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from anomaly_detector import detect_anomalies  # noqa: E402

# ── Discover fixtures ─────────────────────────────────────────────────────────
_GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"
_FIXTURES = sorted(_GOLDEN_DIR.glob("*.json"))

assert _FIXTURES, f"No golden fixtures found in {_GOLDEN_DIR}"


def _load(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _idfn(path):
    return path.stem  # use filename stem as the test id


@pytest.mark.parametrize("fixture_path", _FIXTURES, ids=_idfn)
def test_golden_anomaly(fixture_path: pathlib.Path) -> None:
    """
    Run detect_anomalies against each golden fixture and verify that the
    returned anomaly list matches every assertion in the 'expected' block.
    """
    data = _load(fixture_path)
    zone_id = data["zone_id"]
    raw     = data["raw"]
    exp     = data["expected"]

    anomalies = detect_anomalies(raw, zone_id=zone_id)

    # ── 1. Exact or minimum count ─────────────────────────────────────────────
    if "anomaly_count" in exp:
        assert len(anomalies) == exp["anomaly_count"], (
            f"[{fixture_path.stem}] expected exactly {exp['anomaly_count']} anomalies, "
            f"got {len(anomalies)}: {[a['variable'] for a in anomalies]}"
        )
    if "anomaly_count_min" in exp:
        assert len(anomalies) >= exp["anomaly_count_min"], (
            f"[{fixture_path.stem}] expected at least {exp['anomaly_count_min']} anomalies, "
            f"got {len(anomalies)}: {[(a['factor'], a['variable'], a['severity']) for a in anomalies]}"
        )

    # ── 2. Required anomalies (must_include) ──────────────────────────────────
    for req in exp.get("must_include", []):
        matches = [
            a for a in anomalies
            if (
                a["factor"]   == req["factor"]
                and a["severity"] == req["severity"]
                and a["variable"] == req["variable"]
            )
        ]
        assert matches, (
            f"[{fixture_path.stem}] missing required anomaly "
            f"factor={req['factor']!r} severity={req['severity']!r} variable={req['variable']!r}. "
            f"Actual anomalies: {[(a['factor'], a['variable'], a['severity']) for a in anomalies]}"
        )

    # ── 3. Collect all recommended_action strings ──────────────────────────────
    all_actions = " ".join(
        a.get("recommended_action", "") for a in anomalies
    ).lower()

    # ── 4. Indian localisation: forbidden UK terms ────────────────────────────
    for bad_term in exp.get("no_india_terms", []):
        assert bad_term.lower() not in all_actions, (
            f"[{fixture_path.stem}] UK term '{bad_term}' should have been localised "
            f"for IN_ zone '{zone_id}' but was found in recommended_action text."
        )

    # ── 5. Indian localisation: required local terms ──────────────────────────
    required_terms = exp.get("india_terms_required", [])
    if required_terms:
        found_any = any(t.lower() in all_actions for t in required_terms)
        assert found_any, (
            f"[{fixture_path.stem}] None of the expected India-localised terms "
            f"{required_terms} found in recommended_action text for zone '{zone_id}'. "
            f"Actions: {all_actions[:500]!r}"
        )

    # ── 6. European zone: India terms must NOT appear ────────────────────────
    for bad_term in exp.get("india_terms_must_not_appear", []):
        assert bad_term.lower() not in all_actions, (
            f"[{fixture_path.stem}] Indian term '{bad_term}' must not appear in "
            f"recommended_action for EU zone '{zone_id}' (localisation must be a no-op)."
        )

    # ── 7. European zone: UK terms MUST survive ───────────────────────────────
    uk_terms = exp.get("uk_terms_required", [])
    if uk_terms:
        found_any = any(t.lower() in all_actions for t in uk_terms)
        assert found_any, (
            f"[{fixture_path.stem}] None of the expected UK terms "
            f"{uk_terms} found in recommended_action text for non-IN_ zone '{zone_id}'. "
            f"Actions: {all_actions[:500]!r}"
        )

    # ── 8. Severity ordering: CRITICAL always before WARNING ─────────────────
    sev_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    if len(anomalies) >= 2:
        for i in range(len(anomalies) - 1):
            curr = sev_order.get(anomalies[i]["severity"], 3)
            nxt  = sev_order.get(anomalies[i + 1]["severity"], 3)
            assert curr <= nxt, (
                f"[{fixture_path.stem}] Anomaly list is not sorted by severity. "
                f"Got {anomalies[i]['severity']!r} at index {i} before "
                f"{anomalies[i+1]['severity']!r} at index {i+1}."
            )
