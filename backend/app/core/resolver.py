"""Universal geo-resolver.

The covered-city list is a gatekeeper: a point outside its 8 bounding boxes is refused,
which is why most of Tamil Nadu and India returns "not covered". This resolver answers the
only questions the universal baseline engine needs about an arbitrary point — is it in
India, and what do we call the place — without claiming survey coverage we do not have.

Naming is best-effort (Photon reverse geocode) and never blocks a score: on any failure the
point is still named from its coordinates and scored on terrain + OpenStreetMap.
"""
import threading

import httpx

PHOTON_REVERSE = "https://photon.komoot.io/reverse"
_HEADERS = {"User-Agent": "TerrisIQ/1.0 (property risk screening)"}

# Generous mainland + islands bbox. Points inside it but outside a covered city get the
# universal BASELINE read instead of a 422; points outside it (and outside the US) are not
# in scope and still fall through to the nearest-city message.
_INDIA_BBOX = (6.5, 68.0, 37.5, 97.5)  # lat_min, lng_min, lat_max, lng_max

_cache = {}
_cache_lock = threading.Lock()
_CACHE_LIMIT = 4000


def in_india(lat, lng):
    lat_min, lng_min, lat_max, lng_max = _INDIA_BBOX
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def _fallback(lat, lng):
    return {"name": "%.4f, %.4f" % (lat, lng), "locality": None, "district": None,
            "state": None, "urban_class": "unknown", "source": None}


def resolve_region(lat, lng, timeout=4.0):
    """Best-effort place identity for an arbitrary Indian point.

    Returns {name, locality, district, state, urban_class, source}. `name` is always set
    (coordinates if nothing better), so a caller can label the result even offline.
    """
    key = "%.4f,%.4f" % (round(lat, 4), round(lng, 4))
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit

    region = _fallback(lat, lng)
    try:
        resp = httpx.get(PHOTON_REVERSE, params={"lat": lat, "lon": lng, "lang": "en"},
                         headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        feats = resp.json().get("features", [])
        if feats:
            p = feats[0].get("properties", {})
            locality = (p.get("city") or p.get("town") or p.get("village")
                        or p.get("name") or p.get("locality"))
            district = p.get("county") or p.get("district")
            state = p.get("state")
            region = {
                "name": locality or district or state or region["name"],
                "locality": locality, "district": district, "state": state,
                # OSM place=city/town/village is a decent urban/rural proxy for build rules.
                "urban_class": {"city": "urban", "town": "urban",
                                "village": "rural"}.get(p.get("osm_value"), "unknown"),
                "source": "photon_reverse",
            }
    except Exception:  # noqa: BLE001 - naming must never block a score
        pass

    with _cache_lock:
        if len(_cache) >= _CACHE_LIMIT:
            _cache.clear()
        _cache[key] = region
    return region
