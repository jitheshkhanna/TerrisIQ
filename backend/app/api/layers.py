"""Serve the simplified GeoJSON map layers."""
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core import cities as city_registry
from app.core.geo import PROCESSED_DIR

router = APIRouter(prefix="/api/v1", tags=["layers"])

MAP_DIR = os.path.join(PROCESSED_DIR, "map")

LAYERS = {
    "flood_zones": "Graded flood inundation categories",
    "swd": "Storm water drain network",
    "waterbodies": "Rivers, canals, lakes and marsh (OpenStreetMap)",
    "industrial": "Industrial land use (OpenStreetMap)",
    "flood_hotspots": "Recorded flooding points",
    "industrial_clusters": "CPCB-flagged industrial clusters",
    "dumpsites": "Municipal dumpyards with leachate buffers",
    "wards": "Municipal ward boundaries",
    "zones": "Municipal zone boundaries",
    "low_lying": "Mapped low-lying ground",
}

_memo = {}


def _path(city_slug, name):
    return os.path.join(MAP_DIR, "%s_%s.geojson" % (city_slug, name))


@router.get("/layers")
async def list_layers(city: str = city_registry.DEFAULT_CITY):
    target = city_registry.get(city)
    if target is None:
        raise HTTPException(status_code=404, detail="Unknown city '%s'" % city)
    out = []
    for name, description in LAYERS.items():
        path = _path(target.slug, name)
        out.append({"name": name, "description": description,
                    "available": os.path.exists(path),
                    "size_bytes": os.path.getsize(path) if os.path.exists(path) else 0})
    return {"city": target.slug, "layers": out}


@router.get("/layers/{city}/{name}")
async def get_layer(city: str, name: str):
    target = city_registry.get(city)
    if target is None:
        raise HTTPException(status_code=404, detail="Unknown city '%s'" % city)
    if name not in LAYERS:
        raise HTTPException(status_code=404, detail="Unknown layer '%s'" % name)
    key = "%s/%s" % (target.slug, name)
    if key in _memo:
        return JSONResponse(content=_memo[key])
    path = _path(target.slug, name)
    if not os.path.exists(path):
        # A city legitimately may not have this layer at all.
        return JSONResponse(content={"type": "FeatureCollection", "features": []})
    with open(path) as fh:
        payload = json.load(fh)
    _memo[key] = payload
    return JSONResponse(content=payload)
