"""
loadtest/locustfile.py
────────────────────────────────────────────────────────────────────────────
Locust load testing script for PolyNexus API.

Expected targets (when POLYNEXUS_MOCK_EXTERNAL=1):
  - P95 latency < 500ms
  - P99 latency < 1000ms
  - Throughput: 100 RPS minimum on a single instance

Rate limiting note
──────────────────
The /v1/analyse endpoint defaults to 5 req/min per source IP.  To run a
meaningful load test without hitting that ceiling, set
ANALYSE_RATE_LIMIT on the **server** side:

    ANALYSE_RATE_LIMIT=200/minute python -m uvicorn api:app --port 8000

This env var is never on by default — it must be explicitly set so it
cannot accidentally reach production.

Each simulated Locust user also injects a unique X-Forwarded-For header so
requests are bucketed per-user (not per-process) even when all workers
share the same TCP source address.  This ensures the rate limiter sees
distinct client identities without requiring a real reverse proxy.

Circuit Breaker & Fallback Test Scenarios:
  If running without POLYNEXUS_MOCK_EXTERNAL=1 (live mode), external APIs
  will rate-limit or timeout rapidly under load. This allows observing:
  1. Circuit breakers tripping for SoilGrids/NASA Power.
  2. Fallback to OpenLandMap / Open-Meteo Agro logic.
  3. The `analyse` endpoint remaining stable and returning `200 OK` with
     lower `data_quality` labels instead of cascading `500` errors.

To run (requires locust in venv):
  1. Start the API with mock + relaxed rate limit:
     POLYNEXUS_MOCK_EXTERNAL=1 ANALYSE_RATE_LIMIT=200/minute \\
         python -m uvicorn api:app --port 8000
  2. Run locust:
     python -m locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000 \\
         --headless -u 10 -r 2 -t 30s
"""

import os
import random
from locust import HttpUser, task, between

# Real representative lat/lon per preset zone (matches PRESET_ZONES in api.py)
PRESET_ZONES = [
    {"zone_id": "IN_KA_01", "lat": 15.4589, "lon": 75.0078},
    {"zone_id": "IN_RJ_01", "lat": 27.2152, "lon": 77.4941},
    {"zone_id": "IN_UP_01", "lat": 26.9124, "lon": 80.7145},
    {"zone_id": "IN_GJ_01", "lat": 22.7319, "lon": 71.6482},
    {"zone_id": "IN_WB_01", "lat": 23.2324, "lon": 87.8615},
    {"zone_id": "IN_KL_01", "lat":  9.8482, "lon": 77.0005},
    {"zone_id": "IN_HP_01", "lat": 31.1048, "lon": 77.1734},
    {"zone_id": "IN_MH_01", "lat": 21.1458, "lon": 79.0882},
    {"zone_id": "IN_MP_01", "lat": 23.8388, "lon": 78.7378},
    {"zone_id": "IN_BR_01", "lat": 26.1209, "lon": 85.3647},
    {"zone_id": "IN_TN_01", "lat": 10.6591, "lon": 77.0089},
    {"zone_id": "IN_PB_01", "lat": 30.9010, "lon": 75.8573},
    {"zone_id": "IN_AS_01", "lat": 27.4728, "lon": 94.9120},
    {"zone_id": "IN_TG_01", "lat": 18.6725, "lon": 78.0941},
    {"zone_id": "IN_JK_01", "lat": 34.0152, "lon": 74.9315},
]


class PolyNexusUser(HttpUser):
    # Simulate a user thinking for 1-3 seconds between actions
    wait_time = between(1.0, 3.0)

    def on_start(self):
        """
        Assign each simulated user a unique fake IP.
        This causes slowapi to rate-limit per virtual user rather than per
        process, so the 10-user load test does not pile all requests onto a
        single rate-limit bucket.  The server must have TRUSTED_PROXY_CIDR
        unset (or set to include 127.0.0.1) for this to take effect; the
        header is ignored when the peer is not a trusted proxy.
        """
        # Spread across 10.x.x.x space — guaranteed non-routable RFC1918
        octet2 = random.randint(0, 255)
        octet3 = random.randint(0, 255)
        octet4 = random.randint(1, 254)
        self._fake_ip = f"10.{octet2}.{octet3}.{octet4}"

        # Read key from env (set POLYNEXUS_API_KEY before starting Locust)
        self._api_key = os.environ.get("POLYNEXUS_API_KEY", "dev-api-key")

    def _headers(self) -> dict:
        return {
            "X-API-Key": self._api_key,
            "X-Forwarded-For": self._fake_ip,
        }

    @task(3)
    def view_dashboard(self):
        """Simulate loading the main dashboard for a preset zone."""
        zone = random.choice(PRESET_ZONES)
        self.client.get(
            f"/analyse?zone_id={zone['zone_id']}&lat={zone['lat']}&lon={zone['lon']}",
            headers=self._headers(),
            name="/analyse",
        )

    @task(1)
    def compare_zones(self):
        """Simulate the comparison view."""
        zones = random.sample([z["zone_id"] for z in PRESET_ZONES], 2)
        self.client.post(
            "/compare",
            json={"zone_ids": zones},
            headers=self._headers(),
            name="/compare",
        )

    @task(1)
    def get_zone_observations(self):
        """Simulate viewing the interventions/observations log for a zone."""
        zone = random.choice(PRESET_ZONES)
        self.client.get(
            f"/zones/{zone['zone_id']}/observations",
            headers=self._headers(),
            name="/zones/{zone_id}/observations",
        )
