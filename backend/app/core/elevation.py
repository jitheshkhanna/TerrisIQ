"""SRTM elevation lookups via the Open Topo Data public API.

We deliberately do not ship a clipped GeoTIFF: the `elevation` package shells out to
GDAL, which is not installable in this environment without system packages. Open Topo
Data serves the same SRTM 30m product over HTTP with no auth.

Absolute height above sea level matters far less for urban flooding than height
*relative to the immediate surroundings* - a plot two metres below its neighbours
collects their runoff. So each lookup requests a 9-point stencil (the parcel plus a
ring at ~250 m) in a single batched call and reports the difference.
"""
import json
import math
import os
import threading
import time

import httpx

API_URL = "https://api.opentopodata.org/v1/srtm30m"
RING_M = 250.0
# A second, wider ring. 250 m of relief in a city like Bengaluru is largely SRTM noise:
# Bellandur measures 2.8 m *above* its 250 m ring and still floods every monsoon,
# because it sits at the bottom of a catchment the narrow ring cannot see. The 1 km ring
# is what tells you whether water drains toward a plot or away from it.
WIDE_RING_M = 1000.0
CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "elevation_cache_v2.json")

# Public instance allows 1 call/sec and 100 locations per call.
_MIN_INTERVAL = 1.1
_lock = threading.Lock()
_last_call = [0.0]
_cache = None
_cache_dirty = [False]


def _load_cache():
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(CACHE_PATH) as fh:
            _cache = json.load(fh)
    except Exception:
        _cache = {}
    return _cache


def _save_cache():
    if not _cache_dirty[0]:
        return
    try:
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(_cache, fh)
        os.replace(tmp, CACHE_PATH)
        _cache_dirty[0] = False
    except Exception:
        pass


def _cache_key(lat, lng):
    # ~30 m grid, matching SRTM's own resolution.
    return "%.4f,%.4f" % (round(lat, 4), round(lng, 4))


def _ring(lat, lng, radius_m=RING_M, n=8):
    """n points on a circle of radius_m around (lat, lng)."""
    out = []
    dlat = radius_m / 111320.0
    dlng = radius_m / (111320.0 * max(math.cos(math.radians(lat)), 0.1))
    for i in range(n):
        theta = 2 * math.pi * i / n
        out.append((lat + dlat * math.sin(theta), lng + dlng * math.cos(theta)))
    return out


def _fetch(points, timeout=12.0):
    """Query Open Topo Data for a list of (lat, lng). Returns list of elevations."""
    locations = "|".join("%.6f,%.6f" % (la, lo) for la, lo in points)
    with _lock:
        wait = _MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
    resp = httpx.get(API_URL, params={"locations": locations}, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "OK":
        raise RuntimeError("open topo data: %s" % payload.get("error", "unknown"))
    return [r.get("elevation") for r in payload.get("results", [])]


def elevation_profile(lat, lng):
    """Return elevation context for a parcel.

    {
      "elevation_m": float | None,          # SRTM height at the parcel
      "neighbourhood_mean_m": float | None, # mean of the 250 m ring
      "relative_m": float | None,           # parcel minus ring mean; negative = a hollow
      "source": "srtm30m via opentopodata" | "cache" | None,
      "available": bool,
    }
    """
    cache = _load_cache()
    key = _cache_key(lat, lng)
    if key in cache:
        cached = dict(cache[key])
        cached["source"] = "cache"
        return cached

    # One request covers the parcel plus both rings: 17 points, well inside the API's
    # 100-location limit.
    near = _ring(lat, lng, RING_M)
    wide = _ring(lat, lng, WIDE_RING_M)
    points = [(lat, lng)] + near + wide
    try:
        elevations = _fetch(points)
    except Exception as exc:  # noqa: BLE001 - elevation is a contributing signal, not a hard dependency
        return {"elevation_m": None, "neighbourhood_mean_m": None, "relative_m": None,
                "source": None, "available": False, "error": str(exc)}

    values = [e for e in elevations if e is not None]
    if not values:
        return {"elevation_m": None, "neighbourhood_mean_m": None, "relative_m": None,
                "source": None, "available": False, "error": "no data"}

    here = elevations[0]
    n = len(near)
    ring = [e for e in elevations[1:1 + n] if e is not None]
    ring_wide = [e for e in elevations[1 + n:] if e is not None]
    ring_mean = sum(ring) / len(ring) if ring else None
    wide_mean = sum(ring_wide) / len(ring_wide) if ring_wide else None
    result = {
        "elevation_m": here,
        "neighbourhood_mean_m": round(ring_mean, 2) if ring_mean is not None else None,
        "relative_m": (round(here - ring_mean, 2)
                       if (here is not None and ring_mean is not None) else None),
        "catchment_mean_m": round(wide_mean, 2) if wide_mean is not None else None,
        "relative_catchment_m": (round(here - wide_mean, 2)
                                 if (here is not None and wide_mean is not None) else None),
        "source": "srtm30m via opentopodata",
        "available": here is not None,
    }
    cache[key] = {k: v for k, v in result.items() if k != "source"}
    _cache_dirty[0] = True
    _save_cache()
    return result
