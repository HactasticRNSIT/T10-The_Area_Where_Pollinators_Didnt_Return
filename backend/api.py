"""
api.py
======
Thin FastAPI REST layer that wraps the existing analyse_zone() pipeline.

Endpoints:
  GET /            → serves frontend/index.html
  GET /health      → liveness probe
  GET /analyse     → run full analysis for a zone
  GET /zones       → list preset zones

Usage:
  cd backend
  uvicorn api:app --reload --port 8000
"""

import logging
import sys

from dotenv import load_dotenv

load_dotenv()

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from main import analyse_zone

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)

app = FastAPI(
    title="PolyNexus API",
    description="Pollinator Ecosystem Analysis Platform REST API",
    version="1.0.0",
)

# Allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Serve frontend static files ─────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# ── Preset zones ──────────────────────────────────────────────────────────────

PRESET_ZONES = [
    # ── India ──────────────────────────────────────────────────────────────────
    # Sunflower belt — Karnataka Deccan Plateau (major bee-dependent oilseed)
    {"zone_id": "IN_KA_01", "name": "Sunflower Belt — Dharwad, Karnataka",    "lat": 15.4589, "lon": 75.0078},
    # Mustard/Rapeseed — Rajasthan drylands (huge pollinator demand, Feb–Mar bloom)
    {"zone_id": "IN_RJ_01", "name": "Mustard Belt — Bharatpur, Rajasthan",    "lat": 27.2152, "lon": 77.4941},
    # Mango orchards — Malihabad UP (world's largest mango cluster, bee-critical)
    {"zone_id": "IN_UP_01", "name": "Mango Orchards — Malihabad, Uttar Pradesh","lat": 26.9124,"lon": 80.7145},
    # Cotton Bt — Gujarat (semi-arid, neonicotinoid use; high pesticide stress)
    {"zone_id": "IN_GJ_01", "name": "Cotton Belt — Surendranagar, Gujarat",   "lat": 22.7319, "lon": 71.6482},
    # Boro Rice — West Bengal floodplain (waterlogged soil, low nesting sites)
    {"zone_id": "IN_WB_01", "name": "Rice Belt — Bardhaman, West Bengal",     "lat": 23.2324, "lon": 87.8615},
    # Spice coast — cardamom & pepper hills (high biodiversity, forest margin)
    {"zone_id": "IN_KL_01", "name": "Spice Coast — Idukki, Kerala",           "lat": 9.8482,  "lon": 77.0005},
    # Apple orchards — cold Himachal valley (bee-managed hives, May bloom)
    {"zone_id": "IN_HP_01", "name": "Apple Orchards — Shimla, Himachal Pradesh","lat": 31.1048,"lon": 77.1734},
    # Citrus belt — Vidarbha Maharashtra (orange groves, moderate pesticide use)
    {"zone_id": "IN_MH_01", "name": "Citrus Belt — Nagpur, Maharashtra",      "lat": 21.1458, "lon": 79.0882},
    # Sesame farms — Madhya Pradesh semi-arid (pollinator-sensitive oilseed)
    {"zone_id": "IN_MP_01", "name": "Sesame Farms — Sagar, Madhya Pradesh",   "lat": 23.8388, "lon": 78.7378},
    # Lychee belt — North Bihar alluvial plains (fragrant bloom, bee-critical)
    {"zone_id": "IN_BR_01", "name": "Lychee Belt — Muzaffarpur, Bihar",       "lat": 26.1209, "lon": 85.3647},
]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "polynexus-api"}


@app.get("/zones")
def list_zones():
    return {"zones": PRESET_ZONES}


@app.get("/analyse")
def analyse(
    zone_id: str = Query(..., description="Zone identifier, e.g. FARM_A"),
    lat: float  = Query(..., ge=-90.0, le=90.0,    description="Latitude in decimal degrees"),
    lon: float  = Query(..., ge=-180.0, le=180.0,  description="Longitude in decimal degrees"),
):
    """Run the full 5-factor pollinator ecosystem analysis for the given zone."""
    try:
        result = analyse_zone(zone_id=zone_id, lat=lat, lon=lon)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
