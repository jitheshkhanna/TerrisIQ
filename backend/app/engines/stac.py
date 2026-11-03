"""STAC adapter — real satellite granule provenance over plain HTTPS (no GDAL/rasterio).

The blueprint wants every orbital number cited to its exact granule ID, sensor and timestamp.
Full raster processing is Phase B (GPU/GDAL), but we can already show the *provenance* now:
query a public STAC API over HTTP for the scenes that actually cover a point, and surface their
granule IDs, acquisition timestamps and cloud cover in the Evidence drawer.

Source: Element84 Earth Search (https://earth-search.aws.element84.com/v1) — a public STAC API
over the AWS open-data Sentinel mirror, no auth, global. Called server-side so it is unaffected
by browser CORS. Returns [] (never raises) on any network/parse failure, so the drawer degrades
gracefully rather than breaking the page.
"""
import httpx

_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
# Optical Sentinel-2 (cloud cover meaningful) and C-band Sentinel-1 SAR (all-weather).
_COLLECTIONS = ["sentinel-2-l2a", "sentinel-1-grd"]
_TIMEOUT = 12.0


def _bbox_around(lat: float, lng: float, half_deg: float = 0.02):
    return [lng - half_deg, lat - half_deg, lng + half_deg, lat + half_deg]


def recent_scenes(lat: float, lng: float, limit: int = 6) -> list:
    """Most recent STAC scenes covering the point, newest first. Each item carries the granule
    id, collection, datetime, platform and (optical only) cloud cover — honest provenance for
    the UI. Empty list on any failure."""
    body = {
        "collections": _COLLECTIONS,
        "bbox": _bbox_around(lat, lng),
        "limit": max(1, min(limit, 20)),
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    try:
        resp = httpx.post(_SEARCH_URL, json=body, timeout=_TIMEOUT,
                          headers={"Accept": "application/geo+json"})
        if resp.status_code >= 400:
            return []
        feats = resp.json().get("features", [])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []

    out = []
    for f in feats[:limit]:
        props = f.get("properties", {}) or {}
        cloud = props.get("eo:cloud_cover")
        out.append({
            "granule_id": f.get("id"),
            "collection": (f.get("collection") or
                           (f.get("collections") or [None])[0]),
            "datetime": props.get("datetime"),
            "platform": props.get("platform") or props.get("constellation"),
            "instrument": (props.get("instruments") or [None])[0],
            "cloud_cover_pct": round(cloud, 1) if isinstance(cloud, (int, float)) else None,
        })
    return out
