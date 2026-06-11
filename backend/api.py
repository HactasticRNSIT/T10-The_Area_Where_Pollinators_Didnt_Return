"""
api.py — Fix 2: Pydantic input validation added to /analyse endpoint.
Stops 500 crashes from malformed inputs; returns clean 422 with field-level errors.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
import json as _json
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Depends, Request, Security, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from main import analyse_zone

FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

# ── Logging bootstrap (4.3) ───────────────────────────────────────────────────
# STRUCTURED_LOG=true  → emit one JSON object per line (for Loki / ELK / etc.)
# LOG_LEVEL=INFO       → also capture INFO-level audit records from main.py
# Default stays as human-readable WARNING for local dev.

_STRUCTURED = os.environ.get("STRUCTURED_LOG", "false").lower() in {"true", "1", "yes"}
_LOG_LEVEL  = getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING)


class _JsonFormatter(logging.Formatter):
    """
    Emit one JSON object per log line.
    If the LogRecord carries an ``audit`` extra dict its fields are merged
    into the top-level object so log aggregators can index them directly
    without string parsing.
    """
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "audit") and isinstance(record.audit, dict):
            payload.update(record.audit)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return _json.dumps(payload, ensure_ascii=False)


if _STRUCTURED:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(_JsonFormatter())
    logging.root.handlers = [_handler]
    logging.root.setLevel(_LOG_LEVEL)
else:
    logging.basicConfig(
        level=_LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


# ── Startup validation (Fix 6.1) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Check required environment variables at startup to catch misconfiguration
    before any traffic arrives."""
    _log = logging.getLogger("polynexus.startup")
    if not os.environ.get("POLYNEXUS_API_KEY"):
        _log.warning(
            "POLYNEXUS_API_KEY is not set — all /analyse requests will return 503 "
            "until this variable is configured."
        )
    # Fix 4.4: warn when CORS_ORIGINS is the dev-only default
    if not os.environ.get("CORS_ORIGINS"):
        _log.warning(
            "CORS_ORIGINS env var is not set; defaulting to http://localhost:5173 (development only). "
            "Set CORS_ORIGINS to your production frontend origin before going live."
        )
    if not os.environ.get("TRUSTED_PROXY_CIDR"):
        _log.warning(
            "TRUSTED_PROXY_CIDR is not set. IP-based rate limiting may be spoofable if "
            "the reverse proxy does not strip incoming X-Forwarded-For headers."
        )
    yield


app = FastAPI(
    title="PolyNexus API",
    description="Pollinator Ecosystem Analysis Platform REST API",
    version="1.0.0",
    lifespan=lifespan,
)

# 4.1: Prometheus metrics
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    from metrics import polynexus_groq_calls, polynexus_groq_fallback

    _instrumentator = Instrumentator().instrument(app)
    _instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
except ImportError:
    pass


# Fix 2.3: Hardened IP extraction
import ipaddress
_TRUSTED_PROXY_CIDR = os.environ.get("TRUSTED_PROXY_CIDR")
_trusted_network = ipaddress.ip_network(_TRUSTED_PROXY_CIDR) if _TRUSTED_PROXY_CIDR else None

def _get_real_ip(request: Request) -> str:
    # X-Real-IP is injected by nginx/caddy with the actual client IP (single proxy)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ips = [ip.strip() for ip in forwarded_for.split(",")]
        if _trusted_network:
            try:
                last_hop = ipaddress.ip_address(ips[-1])
                if last_hop in _trusted_network:
                    return ips[0]
            except ValueError:
                pass
        else:
            return ips[0]
    return get_remote_address(request)

limiter = Limiter(key_func=_get_real_ip)
app.state.limiter = limiter

def _custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    response = JSONResponse(
        {"detail": f"Rate limit exceeded: {exc.detail}"}, status_code=429
    )
    # Ensure Retry-After header is present
    if hasattr(exc, "headers") and exc.headers:
        for k, v in exc.headers.items():
            response.headers[k] = str(v)
    else:
        response.headers["Retry-After"] = "1"
    return response

app.add_exception_handler(RateLimitExceeded, _custom_rate_limit_exceeded_handler)

ANALYSE_RATE_LIMIT = os.environ.get("ANALYSE_RATE_LIMIT", "1/second")

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())[:8]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
        if os.environ.get("HSTS_ENABLED", "false").lower() == "true":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

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

class CompareRequest(BaseModel):
    zone_ids: list[str] = Field(..., min_length=1, max_length=6,
                                 description="List of zone_ids to compare (max 6)")
    
    @field_validator("zone_ids")
    @classmethod
    def validate_zone_ids(cls, v):
        import re
        for zid in v:
            if not re.match(r"^[A-Za-z0-9_\-]+$", zid):
                raise ValueError(f"Invalid zone_id format: {zid}")
        return v

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)

class ChatResponse(BaseModel):
    reply: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

from fastapi.security.api_key import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(api_key: str = Security(API_KEY_HEADER)) -> None:
    expected = os.environ.get("POLYNEXUS_API_KEY", "")
    if not expected:
        # Fix 2.1: raise HTTPException instead of RuntimeError so FastAPI handles
        # it gracefully and no stack trace is leaked to the client.
        raise HTTPException(
            status_code=503,
            detail="Service not configured — API key not set. Contact the administrator.",
        )
    if not secrets.compare_digest(api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

ADMIN_KEY_HEADER = APIKeyHeader(name="X-Admin-Key", auto_error=False)

def require_admin_key(api_key: str = Security(ADMIN_KEY_HEADER)) -> None:
    expected = os.environ.get("POLYNEXUS_ADMIN_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin access not configured.",
        )
    if not secrets.compare_digest(api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing Admin key")

@app.post("/admin/cache/clear", dependencies=[Depends(require_admin_key)])
def admin_clear_cache():
    import data_fetcher
    import geo_classifier
    
    data_fetcher.clear_data_cache()
    geo_classifier.clear_crop_cache()
    
    return {
        "cleared": ["data_cache", "crop_cache"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/healthz")
def healthz():
    import history_store
    try:
        # Check DB connectivity
        with history_store._get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Database connectivity failed")
    return {"status": "ok", "service": "polynexus-api"}

@app.get("/readyz")
def readyz():
    from config import _ZONE_WEIGHT_OVERRIDES, API_ENDPOINTS
    if not _ZONE_WEIGHT_OVERRIDES:
        raise HTTPException(status_code=500, detail="_ZONE_WEIGHT_OVERRIDES is empty")
    if "osm_overpass" not in API_ENDPOINTS:
        raise HTTPException(status_code=500, detail="osm_overpass not in API_ENDPOINTS")
    return {"status": "ready"}


@app.get("/zones")
def list_zones():
    return {"zones": PRESET_ZONES}


@app.get("/analyse", dependencies=[Depends(require_api_key)])
@limiter.limit("5/minute")
async def analyse(
    request: Request,
    params: AnalyseParams = Depends()
):
    """
    Run the full 5-factor pollinator ecosystem analysis for the given zone.
    Fix 2: lat/lon/zone_id are validated via FastAPI's Annotated Query
    constraints; invalid inputs return HTTP 422 with field-level detail
    instead of crashing with HTTP 500.
    """
    try:
        result = await analyse_zone(zone_id=params.zone_id.strip(), lat=params.lat, lon=params.lon)
        return result
    except Exception as exc:
        logging.getLogger(__name__).exception("analyse_zone failed for zone=%s lat=%s lon=%s", params.zone_id, params.lat, params.lon)
        raise HTTPException(status_code=500, detail="Internal analysis error. Please try again.") from exc

@app.post("/compare", dependencies=[Depends(require_api_key)])
@limiter.limit("2/minute")
async def compare_zones(request: Request, payload: CompareRequest):
    start_time = time.monotonic()
    
    zone_targets = []
    zone_not_found = []
    for zid in payload.zone_ids:
        preset = next((p for p in PRESET_ZONES if p["zone_id"] == zid), None)
        if preset:
            zone_targets.append(preset)
        else:
            zone_not_found.append(zid)
            
    import asyncio
    async def _safe_analyse(z):
        try:
            res = await asyncio.wait_for(analyse_zone(z["zone_id"], z["lat"], z["lon"]), timeout=25.0)
            res["zone_id"] = z["zone_id"]
            res["status"] = "ok"
            return res
        except asyncio.TimeoutError:
            return {"zone_id": z["zone_id"], "status": "timeout", "error": "Analysis timed out"}
        except Exception as exc:
            logging.getLogger(__name__).warning("compare: zone %s failed: %s", z["zone_id"], exc)
            return {"zone_id": z["zone_id"], "status": "error", "error": str(exc)}
            
    tasks = [_safe_analyse(z) for z in zone_targets]
    results = list(await asyncio.gather(*tasks)) if tasks else []

    for zid in zone_not_found:
        results.append({"zone_id": zid, "status": "not_found", "error": "Zone not in preset list"})
    def sort_key(r):
        if r["status"] == "ok":
            return (0, r.get("activity_score", 100.0))
        return (1, 100.0)
        
    results.sort(key=sort_key)
    
    wall_clock_ms = int((time.monotonic() - start_time) * 1000)
    
    return {
        "zones": results,
        "completed": sum(1 for r in results if r["status"] == "ok"),
        "total": len(payload.zone_ids),
        "wall_clock_ms": wall_clock_ms
    }

@app.get("/zones/{zone_id}/history", dependencies=[Depends(require_api_key)])
def get_zone_history(zone_id: str, weeks: int = Query(12, ge=1, le=52)):
    import history_store
    history = history_store.get_history(zone_id, limit=weeks)
    return {"zone_id": zone_id, "history": history}

@app.get("/zones/{zone_id}/trend", dependencies=[Depends(require_api_key)])
def get_zone_trend(zone_id: str, weeks: int = Query(12, ge=2, le=52)):
    import history_store
    trend = history_store.get_trend(zone_id, weeks=weeks)
    return {"zone_id": zone_id, "trend": trend}

# ── Intervention tracking (3.3) ───────────────────────────────────────────────

class InterventionRequest(BaseModel):
    intervention: str = Field(..., min_length=1, max_length=256)
    applied_at:   str | None = None   # ISO-8601 date string, optional
    notes:        str | None = Field(None, max_length=1024)


@app.post("/zones/{zone_id}/interventions", dependencies=[Depends(require_api_key)])
def record_intervention(zone_id: str, payload: InterventionRequest):
    import intervention_store
    row_id = intervention_store.record_intervention(
        zone_id=zone_id,
        intervention=payload.intervention,
        applied_at=payload.applied_at,
        notes=payload.notes,
    )
    return {"zone_id": zone_id, "intervention_id": row_id, "status": "recorded"}

@app.get("/zones/{zone_id}/interventions", dependencies=[Depends(require_api_key)])
def list_interventions(zone_id: str):
    import intervention_store
    items = intervention_store.get_interventions(zone_id)
    return {"zone_id": zone_id, "interventions": items}

@app.get("/zones/{zone_id}/interventions/{intervention_id}/outcome",
         dependencies=[Depends(require_api_key)])
def intervention_outcome(zone_id: str, intervention_id: int):
    import intervention_store
    result = intervention_store.get_before_after(zone_id, intervention_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Intervention not found")
    return {"zone_id": zone_id, "intervention_id": intervention_id, "outcome": result}

# ── Calendar export (5.2) ─────────────────────────────────────────────────────

@app.post("/zones/{zone_id}/observations", dependencies=[Depends(require_api_key)])
async def record_zone_observation(
    zone_id: str,
    species_name: str | None = Form(default=None),
    species_count: int | None = Form(default=None, ge=0),
    pollinator_count: int | None = Form(default=None, ge=0),
    notes: str | None = Form(default=None, max_length=1024),
    photo: UploadFile | None = File(default=None),
):
    import observation_store

    photo_filename = None
    if photo is not None and photo.filename:
        safe_name = "".join(ch for ch in Path(photo.filename).name if ch.isalnum() or ch in "._-")
        if not safe_name:
            raise HTTPException(status_code=400, detail="Invalid photo filename")
        upload_dir = BACKEND_DIR.parent / "data" / "observations" / zone_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{int(time.time())}_{safe_name}"
        target.write_bytes(await photo.read())
        photo_filename = str(target)

    observation_id = observation_store.record_observation(
        zone_id=zone_id,
        species_name=species_name,
        species_count=species_count,
        pollinator_count=pollinator_count,
        photo_filename=photo_filename,
        notes=notes,
    )
    return {"zone_id": zone_id, "observation_id": observation_id, "status": "recorded"}


@app.get("/zones/{zone_id}/observations", dependencies=[Depends(require_api_key)])
def list_zone_observations(zone_id: str, limit: int = Query(50, ge=1, le=200)):
    import observation_store
    return {"zone_id": zone_id, "observations": observation_store.get_observations(zone_id, limit=limit)}


from fastapi.responses import Response as _Response

@app.get("/zones/{zone_id}/calendar.ics", dependencies=[Depends(require_api_key)])
@limiter.limit("5/minute")
def get_zone_calendar(
    request: Request,
    zone_id: str,
    lat: float = Query(..., ge=-90.0,  le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
):
    """Generate a .ics advisory calendar for a zone based on its latest analysis."""
    try:
        result = analyse_zone(zone_id=zone_id, lat=lat, lon=lon)
        decision_brief = result.get("decision_brief", {})
        crops = result.get("crop_dependency", {})

        # Find human-readable name from preset
        preset = next((p for p in PRESET_ZONES if p["zone_id"] == zone_id), None)
        zone_name = preset["name"] if preset else zone_id

        from calendar_export import build_advisory_calendar
        ics_bytes = build_advisory_calendar(zone_id, zone_name, decision_brief, crops)
        return _Response(
            content=ics_bytes,
            media_type="text/calendar",
            headers={"Content-Disposition": f'attachment; filename="{zone_id}_advisory.ics"'},
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("calendar export failed for zone=%s", zone_id)
        raise HTTPException(status_code=500, detail="Calendar generation failed.") from exc

@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("5/minute")
def chat(
    request: Request,
    payload: ChatRequest
):
    """
    Mock endpoint for agricultural chatbot.
    """
    req_id = request.headers.get("X-Request-ID", "unknown")
    logging.getLogger(__name__).debug("[chat] req_id=%s raw_msg=%r", req_id, payload.message)

    msg = payload.message.lower()
    
    if "pesticide" in msg or "spray" in msg:
        reply = "To reduce pesticide stress, try adopting Integrated Pest Management (IPM). Limit spraying to early morning or late evening when pollinators are less active, and choose targeted bio-pesticides over broad-spectrum chemicals."
    elif "flower" in msg or "strip" in msg or "habitat" in msg:
        reply = "Planting flower strips or preserving wild hedgerows provides crucial nesting habitats and forage for wild bees, drastically reducing habitat fragmentation stress."
    elif "weather" in msg or "climate" in msg or "temperature" in msg:
        reply = "Extreme heat can cause flowers to drop and reduce nectar production. Consider installing shade nets or using localized micro-irrigation to maintain humidity around the crop canopy during peak heat."
    elif "stress" in msg or "health" in msg:
        reply = "Overall pollinator stress is a combination of pesticide exposure, habitat loss, climate extremes, and poor floral diversity. Look at your PolyNexus dashboard's top risk factor to see what you should address first."
    elif "soil" in msg or "tillage" in msg:
        reply = "Many native bees nest in the ground. Reducing deep tillage and adopting no-till or reduced-till practices can protect these vital ground-nesting populations."
    else:
        reply = "I'm your Agri-Bot! I can help you understand how to reduce pollinator stress, manage pesticide risks, improve floral habitats, or adapt to climate extremes. What would you like to know?"

    return ChatResponse(reply=reply)
