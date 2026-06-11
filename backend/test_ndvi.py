"""
NDVI Integration Verification Script
Run this after deploying the Sentinel Hub integration to confirm it's working.
"""

import os
import sys
from datetime import datetime

# Load env variables since test might run outside uvicorn
from dotenv import load_dotenv
load_dotenv('.env')

from data_fetcher import fetch_agromonitoring_ndvi, _get_copernicus_token

# --- Test 1: Check credentials are loaded ---
def test_credentials_present():
    client_id = os.environ.get("COPERNICUS_CLIENT_ID")
    client_secret = os.environ.get("COPERNICUS_CLIENT_SECRET")
    assert client_id, "COPERNICUS_CLIENT_ID not set"
    assert client_secret, "COPERNICUS_CLIENT_SECRET not set"
    print("[OK] Credentials found in environment")

# --- Test 2: OAuth token fetch works ---
def test_oauth_token():
    token = _get_copernicus_token()
    assert token, "Failed to retrieve OAuth token"
    print(f"[OK] OAuth token retrieved: {token[:10]}...")

# --- Test 3: Real NDVI fetch for IN_HP_01 (Shimla orchard) ---
def test_real_ndvi_fetch():
    # Replace with actual lat/lon for IN_HP_01
    lat, lon = 31.1048, 77.1734  # Shimla approx coordinates

    result = fetch_agromonitoring_ndvi(lat, lon)

    print(f"NDVI value: {result.get('ndvi')}")
    print(f"Source: {result.get('source')}")
    print(f"Scene date: {result.get('scene_date')}")
    print(f"Cloud cover: {result.get('cloud_pct')}")

    assert result.get("source") != "open_meteo_derived_ndvi_proxy", \
        "Still falling back to proxy — check date window logic"

    assert 0 <= result.get("ndvi") <= 1, \
        f"NDVI out of expected range: {result.get('ndvi')}"

    # Sanity check: scene date should be in the past relative to real-world time
    scene_date = datetime.strptime(result.get("scene_date"), "%Y-%m-%d")
    assert scene_date < datetime.now(), \
        "Scene date is in the future — date offset logic is broken"

    print("[OK] Real Sentinel-2 NDVI fetched successfully")

# --- Test 4: Fallback works when Copernicus is unreachable ---
def test_fallback_on_failure(monkeypatch):
    import data_fetcher
    
    # Temporarily break credentials to simulate failure using monkeypatch
    monkeypatch.setattr(data_fetcher, "_get_copernicus_token", lambda: None)
    
    # Clear all data caches to prevent returning result from previous test
    data_fetcher.clear_data_cache()

    lat, lon = 31.1048, 77.1734
    result = fetch_agromonitoring_ndvi(lat, lon)

    print(f"Fallback result: {result}")
    assert result.get("source") == "open_meteo_derived_ndvi_proxy", \
        f"Fallback did not trigger on auth failure. Got: {result.get('source')}"
    assert result.get("ndvi") is not None, \
        "Fallback returned no NDVI value"

    print("[OK] Fallback to proxy works correctly")

# --- Test 5: Token caching (avoid re-fetching every call) ---
def test_token_caching():
    import time

    start = time.time()
    token1 = _get_copernicus_token()
    t1 = time.time() - start

    start = time.time()
    token2 = _get_copernicus_token()
    t2 = time.time() - start

    assert token1 == token2, "Token not cached — different token returned"
    assert t2 < t1 / 2 or t2 < 0.01, "Second call took similar time — caching may not be working"
    print(f"[OK] Token caching works (1st: {t1:.3f}s, 2nd: {t2:.3f}s)")


if __name__ == "__main__":
    print("Running NDVI integration verification...\n")
    test_credentials_present()
    test_oauth_token()
    test_real_ndvi_fetch()
    print("\nSkipping test_fallback_on_failure in standalone mode (requires pytest monkeypatch).")
    test_token_caching()
    print("\n[SUCCESS] All standalone tests passed!")
