"""
api.py — Fix 2: Pydantic input validation added to /analyse endpoint.
Stops 500 crashes from malformed inputs; returns clean 422 with field-level errors.
"""

import logging
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs) -> None:
        return None

BACKEND_DIR = Path(__file__).parent
load_dotenv(BACKEND_DIR / ".env")

import os
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from main import analyse_zone

FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# ── Preset zones ──────────────────────────────────────────────────────────────

PRESET_ZONES = [
    {"zone_id": "IN_KA_01", "name": "Sunflower Belt — Dharwad, Karnataka",     "lat": 15.4589, "lon": 75.0078},
    {"zone_id": "IN_RJ_01", "name": "Mustard Belt — Bharatpur, Rajasthan",     "lat": 27.2152, "lon": 77.4941},
    {"zone_id": "IN_UP_01", "name": "Mango Orchards — Malihabad, Uttar Pradesh","lat": 26.9124, "lon": 80.7145},
    {"zone_id": "IN_GJ_01", "name": "Cotton Belt — Surendranagar, Gujarat",    "lat": 22.7319, "lon": 71.6482},
    {"zone_id": "IN_WB_01", "name": "Rice Belt — Bardhaman, West Bengal",      "lat": 23.2324, "lon": 87.8615},
    {"zone_id": "IN_KL_01", "name": "Spice Coast — Idukki, Kerala",            "lat": 9.8482,  "lon": 77.0005},
    {"zone_id": "IN_HP_01", "name": "Apple Orchards — Shimla, Himachal Pradesh","lat": 31.1048, "lon": 77.1734},
    {"zone_id": "IN_MH_01", "name": "Citrus Belt — Nagpur, Maharashtra",       "lat": 21.1458, "lon": 79.0882},
    {"zone_id": "IN_MP_01", "name": "Sesame Farms — Sagar, Madhya Pradesh",    "lat": 23.8388, "lon": 78.7378},
    {"zone_id": "IN_BR_01", "name": "Lychee Belt — Muzaffarpur, Bihar",        "lat": 26.1209, "lon": 85.3647},
    {"zone_id": "IN_TN_01", "name": "Coconut Groves — Pollachi, Tamil Nadu",   "lat": 10.6591, "lon": 77.0089},
    {"zone_id": "IN_PB_01", "name": "Wheat Heartland — Ludhiana, Punjab",      "lat": 30.9010, "lon": 75.8573},
    {"zone_id": "IN_AS_01", "name": "Tea Gardens — Dibrugarh, Assam",          "lat": 27.4728, "lon": 94.9120},
    {"zone_id": "IN_TG_01", "name": "Turmeric Belt — Nizamabad, Telangana",    "lat": 18.6725, "lon": 78.0941},
    {"zone_id": "IN_JK_01", "name": "Saffron Fields — Pampore, J&K",           "lat": 34.0152, "lon": 74.9315},
]


# ── Fix 2: Pydantic query-param model ─────────────────────────────────────────

class AnalyseParams(BaseModel):
    """
    Validated query parameters for /analyse.
    Pydantic raises RequestValidationError (→ 422) before the handler runs,
    eliminating 500 crashes from bad inputs.
    """
    zone_id: str = Field(..., min_length=1, max_length=64,
                         description="Zone identifier, e.g. IN_KA_01",
                         pattern=r"^[A-Za-z0-9_\-]+$")
    lat: float  = Field(..., ge=-90.0,  le=90.0,  description="Latitude in decimal degrees")
    lon: float  = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")

    @field_validator("zone_id")
    @classmethod
    def strip_zone_id(cls, v: str) -> str:
        return v.strip()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "polynexus-api"}


@app.get("/zones")
def list_zones():
    return {"zones": PRESET_ZONES}


@app.get("/analyse")
def analyse(
    zone_id: Annotated[str, Query(min_length=1, max_length=64,
                                  pattern=r"^[A-Za-z0-9_\-]+$",
                                  description="Zone identifier")],
    lat: Annotated[float, Query(ge=-90.0,  le=90.0,  description="Latitude")],
    lon: Annotated[float, Query(ge=-180.0, le=180.0, description="Longitude")],
):
    """
    Run the full 5-factor pollinator ecosystem analysis for the given zone.
    Fix 2: lat/lon/zone_id are validated via FastAPI's Annotated Query
    constraints; invalid inputs return HTTP 422 with field-level detail
    instead of crashing with HTTP 500.
    """
    try:
        result = analyse_zone(zone_id=zone_id.strip(), lat=lat, lon=lon)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
