"""Evidence provenance endpoints: real satellite scene listings and GeoIntent validation.

Both are the Phase-A, serverless slices of the blueprint's provenance + deterministic-map
goals. Scene listing gives the Evidence drawer genuine granule IDs/timestamps over HTTP (no
GDAL); GeoIntent validation lets the map adapter and the chat agent exchange typed map state.
"""
from fastapi import APIRouter, Query

from app.engines.stac import recent_scenes
from app.models.geoui import GeoIntent

router = APIRouter(prefix="/api/v1", tags=["evidence"])


@router.get("/evidence/scenes")
def scenes(lat: float = Query(..., ge=-90, le=90),
           lng: float = Query(..., ge=-180, le=180),
           limit: int = Query(6, ge=1, le=20)):
    """Recent public Sentinel-1/2 STAC scenes covering the point — granule ID, sensor, time,
    cloud cover. Honest provenance for the Evidence drawer; [] if the STAC API is unreachable."""
    items = recent_scenes(lat, lng, limit)
    return {
        "point": {"lat": lat, "lng": lng},
        "count": len(items),
        "scenes": items,
        "source": "Element84 Earth Search STAC (public Sentinel mirror)",
        "note": ("Scene availability/provenance only. Pixel-level flood/subsidence products "
                 "(NISAR/OPERA/InSAR) are Phase B." if not items else None),
    }


@router.post("/geoui/validate")
def geoui_validate(intent: GeoIntent):
    """Validate and normalize a GeoIntent map-state payload. The frontend map adapter and the
    agent both round-trip through this so neither drives the map by screenshot or DOM click."""
    return {"ok": True, "intent": intent.model_dump(exclude_none=True)}
