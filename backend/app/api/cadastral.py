"""Cadastral & statutory endpoints — the legally-compliant half of the blueprint.

Phase A (serverless, no spatial data) today: the Build Scope development-potential calculator
and its layout export, plus a ULPIN/survey-number lookup that is HONEST about not yet having
an authorized parcel source. The 33-point spatial statutory engine is Phase B (needs digitized
city GIS in PostGIS); it is not stubbed with fake data here.
"""
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.engines import india_hazards
from app.engines.build_scope import build_scope
from app.engines.build_scope_layout import plotted_layout, setback_envelope, to_dxf
from app.engines.us_flood import in_us
from app.models.schemas import BuildScopeRequest

router = APIRouter(prefix="/api/v1/cadastral", tags=["cadastral"])

# ULPIN / Bhu-Aadhaar: a 14-character alphanumeric parcel code. We validate the shape only;
# resolving it to a parcel needs authorized DoLR/API Setu access we do not have yet.
_ULPIN_RE = re.compile(r"^[0-9A-Z]{14}$")

# Tamil Nadu bounding box (approx). Pure + fast so Build Scope stays reactive on every
# keystroke (no network). shortcut: a plot just outside gets the India-generic profile — an
# honest fallback, never a wrong TN number; upgrade to a TN polygon if precision ever matters.
_TN_BBOX = (8.0, 76.2, 13.6, 80.4)  # (min_lat, min_lng, max_lat, max_lng)


def resolve_jurisdiction(lat, lng):
    """Point -> which development-control regime governs it. Default to Tamil Nadu (the only
    jurisdiction with a bundled ruleset) when there is no point to go on."""
    if lat is None or lng is None:
        return "tamil_nadu"
    if in_us(lat, lng):
        return "us"
    la0, lo0, la1, lo1 = _TN_BBOX
    return "tamil_nadu" if (la0 <= lat <= la1 and lo0 <= lng <= lo1) else "india"


def scope_from(req: BuildScopeRequest) -> dict:
    """Build the region-adaptive scope, deriving jurisdiction and the airport NOC from the
    point when present. Shared by the JSON endpoint, the DXF export and the PDF report."""
    jur = (req.jurisdiction or resolve_jurisdiction(req.latitude, req.longitude)).lower()
    airport = (india_hazards.nearest_airport(req.latitude, req.longitude)
               if req.latitude is not None and req.longitude is not None else None)
    return build_scope(
        plot_area_sqm=req.plot_area_sqm, road_width_m=req.road_width_m, use=req.use,
        proposed_height_m=req.proposed_height_m, pte_amsl_m=req.pte_amsl_m,
        ground_elev_amsl_m=req.ground_elev_amsl_m, haca_cap_m=req.haca_cap_m, flags=req.flags,
        jurisdiction=jur, fsi_override=req.fsi_override, airport=airport)


def _layout(req: BuildScopeRequest, scope: dict) -> dict:
    """Build the right layout export for the use: a subdivision for a plotted layout, else
    the single-plot setback envelope."""
    if req.use == "plotted_layout":
        return plotted_layout(req.plot_area_sqm, req.plot_width_m, req.plot_depth_m,
                              road_width_m=max(req.road_width_m, 7.0))
    return setback_envelope(req.plot_area_sqm, scope["setbacks"],
                            req.plot_width_m, req.plot_depth_m)


@router.post("/build-scope")
def build_scope_endpoint(req: BuildScopeRequest):
    """Indicative TNCDBR development envelope + a GeoJSON layout. See build_scope.py for the
    honesty note; every number carries its basis and a verify-with-the-authority disclaimer."""
    try:
        scope = scope_from(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"scope": scope, "layout_geojson": _layout(req, scope)}


@router.post("/build-scope/layout.dxf", response_class=PlainTextResponse)
def build_scope_dxf(req: BuildScopeRequest):
    """The same layout as a downloadable AutoCAD DXF (local planar metres, not georeferenced)."""
    try:
        scope = scope_from(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    dxf = to_dxf(_layout(req, scope))
    return PlainTextResponse(
        dxf, media_type="application/dxf",
        headers={"Content-Disposition": 'attachment; filename="terrisiq_build_scope.dxf"'})


@router.get("/ulpin/{code}")
def ulpin_lookup(code: str):
    """Validate a 14-char ULPIN / Bhu-Aadhaar and report, honestly, that resolving it to a
    parcel awaits authorized DoLR / API Setu access (no scraping). Ships the UX rail now."""
    code = (code or "").strip().upper()
    valid = bool(_ULPIN_RE.match(code))
    return {
        "ulpin": code,
        "valid_format": valid,
        "resolved": False,
        "message": (
            "Valid ULPIN format." if valid else
            "A ULPIN / Bhu-Aadhaar is 14 alphanumeric characters.")
        + " Parcel resolution needs authorized DoLR / NeGD API Setu access, which is not yet "
          "connected. We never scrape state land portals.",
        "next_step": "Drop a pin or upload a consented FMB/Patta to delineate the plot instead.",
    }
