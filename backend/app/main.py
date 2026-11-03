"""Property Risk Analyser API entry point."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import cadastral, chat, documents, evidence, geocode, layers, report, risk
from app.core import config as cfg
from app.core import cities as city_registry
from app.core.geo import CACHE_DIR, get_store, loaded_slugs

app = FastAPI(
    title="Property Risk Analyser",
    version="0.1.0",
    description=(
        "Parcel-level environmental risk screening for Chennai real estate: monsoon "
        "flooding, groundwater contamination and summer water scarcity, scored from "
        "open GCC, CPCB, CGWB, SRTM and OpenStreetMap data."),
)

# Optional shared-key gate. OFF by default, so the public site and existing clients are
# unaffected. Set TERRIS_REQUIRE_KEY=1 and TERRIS_API_KEY=<secret> to require the
# X-Terris-Key header on the scoring/geocoding endpoints (every client must then send it:
# the extension via API_KEY in constants.js, the frontend via the rewrite). Added before
# CORS below so CORS stays outermost and the 401 still carries CORS headers.
_API_KEY = os.environ.get("TERRIS_API_KEY", "")
_REQUIRE_KEY = os.environ.get("TERRIS_REQUIRE_KEY", "").strip().lower() in ("1", "true", "yes", "on")
_PROTECTED_PREFIXES = ("/api/v1/risk", "/api/v1/geocode")


async def _api_key_gate(request, call_next):
    if _REQUIRE_KEY and request.method not in ("OPTIONS", "HEAD"):
        path = request.url.path
        if any(path.startswith(p) for p in _PROTECTED_PREFIXES):
            if not _API_KEY or request.headers.get("x-terris-key", "") != _API_KEY:
                return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key."})
    return await call_next(request)


app.add_middleware(BaseHTTPMiddleware, dispatch=_api_key_gate)

# The GeoJSON layers are the heaviest thing we serve; gzip cuts them by roughly 4x.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(risk.router)
app.include_router(geocode.router)
app.include_router(layers.router)
app.include_router(report.router)
app.include_router(chat.router)
app.include_router(cadastral.router)
app.include_router(documents.router)
app.include_router(evidence.router)


@app.on_event("startup")
def _warm_default_city():
    """Warm Chennai in a BACKGROUND thread so it never blocks cold-start responses. The
    heavy ~26MB load used to run inline here, taxing every cold start — including the
    frequent /geocode type-ahead calls, which need no city data at all. Risk scoring still
    gets a warm store most of the time; the first /risk after a cold start pays the load
    lazily via get_store() if the thread hasn't finished."""
    import threading

    def _warm():
        try:
            get_store(city_registry.get(city_registry.DEFAULT_CITY))
        except Exception:  # noqa: BLE001 - never let warming crash the worker
            pass

    threading.Thread(target=_warm, daemon=True).start()


@app.get("/api/v1/health")
def health():
    """Liveness, plus enough detail to spot a deploy that shipped without its data."""
    import os as _os

    cities_status = {}
    for slug, city in city_registry.CITIES.items():
        cache = _os.path.join(CACHE_DIR, "%s.pkl" % slug)
        cities_status[slug] = {
            "depth": city.depth,
            "cache_present": _os.path.exists(cache),
            "cache_mb": round(_os.path.getsize(cache) / 1e6, 1) if _os.path.exists(cache) else 0,
            "scoreable": city.scoreable_dimensions,
        }
    warm = loaded_slugs()
    detail = {}
    for slug in warm:
        store = get_store(city_registry.get(slug))
        detail[slug] = {name: len(layer) for name, layer in store.layers.items() if len(layer)}

    missing = [s for s, v in cities_status.items() if not v["cache_present"]]
    return {
        "status": "ok" if not missing else "degraded: no cache for %s" % ", ".join(missing),
        "cities": cities_status,
        "loaded": warm,
        "layers": detail,
    }


@app.get("/api/v1/meta")
def meta():
    """Weights, grade bands and data provenance - what the scores are built from."""
    return {
        "weights": {"flood": cfg.WEIGHT_FLOOD,
                    "contamination": cfg.WEIGHT_CONTAMINATION,
                    "scarcity": cfg.WEIGHT_SCARCITY},
        "grade_bands": [{"max_score": c, "grade": g, "band": b}
                        for c, g, b in cfg.GRADE_BANDS],
        "coverage": {c.slug: c.depth for c in city_registry.CITIES.values()},
        "sources": [
            {"name": "GCC flood inundation zones (Chennai only)", "via": "OpenCity.in",
             "licence": "Open",
             "note": "5 categories; validated against 53 recorded 2020 hotspots "
                     "(High+Very High = 10.8% of area, 45% of hotspots)"},
            {"name": "GCC storm water drain network", "via": "OpenCity.in", "licence": "Open",
             "note": "10,255 segments with condition and dimensions"},
            {"name": "GCC 2020 flood hotspots (Cyclone Nivar)", "via": "OpenCity.in",
             "licence": "Open"},
            {"name": "SRTM 30m elevation", "via": "Open Topo Data", "licence": "Public domain"},
            {"name": "Waterbodies, industrial land use, coastline", "via": "OpenStreetMap",
             "licence": "ODbL"},
            {"name": "CPCB CEPI industrial cluster scores", "via": "Curated", "licence": "Public"},
            {"name": "Groundwater status", "via": "Hand-curated", "licence": "Public",
             "note": "4 localities carry a published CGWB/CMWSSB water level; the other 60 "
                     "are inferred from the CGWB regional finding (46 of 51 blocks "
                     "overexploited) and carry no measured value. Nothing is fetched from "
                     "CMWSSB directly. See each record's provenance field."},
        ],
    }
