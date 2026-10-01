"""Address search and reverse lookup, tuned for how buyers actually search.

Photon is the primary geocoder rather than Nominatim because it is built for
type-ahead: it tolerates typos ("velacheri" -> Velachery, "medavakam" -> Medavakkam),
matches partial street names, and indexes landmarks. Nominatim returns nothing for any
of those. Nominatim stays as a fallback for the rare query Photon misses.

Both are free public services. If this ever carries real traffic, self-host Photon -
the API shape here does not change.
"""
import os
import threading
import time

import httpx
from fastapi import APIRouter, HTTPException

from app.core import cities as city_registry
from app.core.places import (CITY_CENTRE, build_label, category_of, expand_query,
                             in_region, relevance, split_anchor)
from app.models.schemas import GeocodeResponse, GeocodeResult

router = APIRouter(prefix="/api/v1", tags=["geocode"])

PHOTON = "https://photon.komoot.io/api/"
PHOTON_REVERSE = "https://photon.komoot.io/reverse"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "TerraRiskAnalyser/0.1 (parcel environmental risk screening)"}

# LocationIQ is a fast, type-ahead-first geocoder with a free tier. When LOCATIONIQ_KEY is
# set it serves the fast (/geocode?fast=1) autocomplete path in a few hundred ms; Photon
# remains the automatic fallback (and the slow public Photon is why we added this at all).
LOCATIONIQ_KEY = os.environ.get("LOCATIONIQ_KEY", "")
LOCATIONIQ_URL = "https://api.locationiq.com/v1/autocomplete"

_cache = {}
_cache_lock = threading.Lock()
CACHE_LIMIT = 2000

# Nominatim's usage policy allows one request per second. Photon has no such limit,
# which is another reason it leads.
_nominatim_lock = threading.Lock()
_nominatim_last = [0.0]


def _cache_get(key):
    with _cache_lock:
        return _cache.get(key)


def _cache_put(key, value):
    with _cache_lock:
        if len(_cache) >= CACHE_LIMIT:
            _cache.clear()
        _cache[key] = value


def _photon_search(query, limit, near=None):
    lat, lon = near or CITY_CENTRE
    resp = httpx.get(PHOTON, params={
        "q": query, "lat": lat, "lon": lon, "limit": limit * 3, "lang": "en",
    }, headers=HEADERS, timeout=8.0)
    resp.raise_for_status()
    return resp.json().get("features", [])


# Below this, the top result does not really contain what the user typed.
WEAK_MATCH = 1.6

# How far from the named area a result may sit and still count as "in" it.
ANCHOR_RADIUS_KM = 3.0


def _km(a_lat, a_lng, b_lat, b_lng):
    """Rough great-circle distance. Good enough for a relevance cutoff."""
    import math
    dlat = math.radians(b_lat - a_lat)
    dlng = math.radians(b_lng - a_lng) * math.cos(math.radians((a_lat + b_lat) / 2))
    return 6371.0 * math.sqrt(dlat * dlat + dlng * dlng)


def _anchored_retry(expanded, limit, bias=None, bounds=None):
    """Resolve the area named in the query, then search for the thing near it.

    "velacheri bus stop" searched flat returns bus stops in Anna Nagar and Adyar: every
    result matches "bus stop" perfectly and nothing anchors it to Velachery. Resolving
    Velachery first and biasing the second search to that point fixes the whole class of
    "<landmark type> in <area>" queries, which is how people actually search.
    """
    area, kind = split_anchor(expanded)
    if not area or not kind:
        return []
    try:
        anchors = _photon_search(area, 1, near=bias)
    except Exception:  # noqa: BLE001
        return []
    for feature in anchors:
        coords = (feature.get("geometry") or {}).get("coordinates")
        if not coords or len(coords) < 2:
            continue
        lng, lat = float(coords[0]), float(coords[1])
        if not in_region(lat, lng, bounds):
            continue
        try:
            found = [r for r in (_from_photon(f, bounds)
                                 for f in _photon_search(expanded, limit, near=(lat, lng))) if r]
        except Exception:  # noqa: BLE001
            found = []

        # Only keep what is genuinely in that area. OSM names few bus stops in Chennai,
        # so an unfiltered search happily returns one 4 km away in another neighbourhood.
        found = [r for r in found
                 if _km(lat, lng, r.latitude, r.longitude) <= ANCHOR_RADIUS_KM]

        # Offer the area itself. If we cannot find the exact landmark, dropping the user
        # on the right neighbourhood beats dropping them on the wrong one.
        anchor_result = _from_photon(feature, bounds)
        if anchor_result:
            found = [anchor_result] + [r for r in found
                                       if r.label.lower() != anchor_result.label.lower()]
        return found
    return []


def _nominatim_search(query, limit):
    with _nominatim_lock:
        wait = 1.1 - (time.time() - _nominatim_last[0])
        if wait > 0:
            time.sleep(wait)
        _nominatim_last[0] = time.time()
    resp = httpx.get(NOMINATIM, params={
        "q": "%s, Chennai" % query, "format": "jsonv2", "limit": limit,
        "countrycodes": "in", "addressdetails": 1,
        "viewbox": "79.80,13.50,80.50,12.50", "bounded": 1,
    }, headers=HEADERS, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _from_photon(feature, bbox=None):
    props = feature.get("properties", {})
    coords = (feature.get("geometry") or {}).get("coordinates")
    if not coords or len(coords) < 2:
        return None
    lng, lat = float(coords[0]), float(coords[1])
    if not in_region(lat, lng, bbox):
        return None
    primary, context = build_label(props)
    return GeocodeResult(label=primary, context=context, category=category_of(props),
                         latitude=lat, longitude=lng, type=props.get("osm_value"))


def _from_nominatim(item, bbox=None):
    try:
        lat, lng = float(item["lat"]), float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not in_region(lat, lng, bbox):
        return None
    address = item.get("address") or {}
    props = {
        "name": item.get("name") or address.get("suburb") or address.get("road"),
        "street": address.get("road"),
        "district": address.get("suburb") or address.get("neighbourhood"),
        "city": address.get("city") or address.get("town"),
        "postcode": address.get("postcode"),
        "osm_key": item.get("category"), "osm_value": item.get("type"),
    }
    primary, context = build_label(props)
    return GeocodeResult(label=primary, context=context, category=category_of(props),
                         latitude=lat, longitude=lng, type=item.get("type"))


def _locationiq(query, limit, bbox):
    """Fast type-ahead via LocationIQ. Biased to the city bbox (not bounded, so a nearby
    match still shows), India only. Returns GeocodeResult list, newest-ranked by LocationIQ."""
    params = {
        "key": LOCATIONIQ_KEY, "q": query, "limit": max(1, min(limit, 10)),
        "countrycodes": "in", "dedupe": 1, "accept-language": "en",
    }
    if bbox:
        # bbox is a tuple (lat_min, lng_min, lat_max, lng_max). LocationIQ viewbox wants
        # min_lon,min_lat,max_lon,max_lat; bounded=0 biases toward the city without excluding.
        lat_min, lng_min, lat_max, lng_max = bbox
        params["viewbox"] = "%f,%f,%f,%f" % (lng_min, lat_min, lng_max, lat_max)
        params["bounded"] = 0
    resp = httpx.get(LOCATIONIQ_URL, params=params, timeout=5.0)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):   # LocationIQ returns {"error": ...} on no-match/limit
        return []
    out = []
    for it in data:
        try:
            lat, lng = float(it["lat"]), float(it["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        primary = it.get("display_place") or (it.get("display_name") or "").split(",")[0]
        context = it.get("display_address") or ""
        if not primary:
            continue
        kind = (it.get("type") or it.get("class") or "place").replace("_", " ").title()
        out.append(GeocodeResult(label=primary, context=context, category=kind,
                                 latitude=lat, longitude=lng, type=it.get("type")))
    return out


def _rank(results, query):
    """Re-rank by how well each result matches the distinctive part of the query,
    keeping the geocoder's own order as the tiebreak."""
    scored = [(relevance(query, r.label, r.context, r.category), -i, r)
              for i, r in enumerate(results)]
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [r for _, _, r in scored]


def _dedupe(results, limit):
    seen, out = set(), []
    for result in results:
        # Same name within ~100 m is the same place described twice.
        key = (result.label.lower(), round(result.latitude, 3), round(result.longitude, 3))
        if key in seen:
            continue
        seen.add(key)
        out.append(result)
        if len(out) >= limit:
            break
    return out


@router.get("/geocode", response_model=GeocodeResponse)
async def geocode(q: str, limit: int = 6, city: str = None, fast: int = 0):
    raw = q.strip()
    # Bias to the selected city, otherwise "MG Road" lands in whichever metro Photon
    # happens to rank first.
    target = city_registry.get(city) if city else None
    bias = target.centre if target else None
    bounds = target.bbox if target else None
    if len(raw) < 2:
        raise HTTPException(status_code=400, detail="Type at least two characters.")
    limit = max(1, min(limit, 10))
    expanded = expand_query(raw) or raw

    # Fast mode (type-ahead): Photon only — skip the anchored retry and the Nominatim
    # fallback (which can add a second or more). Used by the extension popup so suggestions
    # stay snappy; the city bias keeps them accurate.
    key = "s|%s|%d|%s|%d" % (expanded.lower(), limit, target.slug if target else "-", 1 if fast else 0)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Fast path: LocationIQ first (fast, type-ahead), Photon as automatic fallback if the
    # key is unset, LocationIQ errors, or it returns nothing.
    if fast and LOCATIONIQ_KEY:
        try:
            liq = _locationiq(expanded, limit, bounds)
        except Exception:  # noqa: BLE001 - any LocationIQ failure -> fall through to Photon
            liq = []
        if liq:
            response = GeocodeResponse(query=raw, expanded=expanded if expanded != raw else None,
                                       source="locationiq", results=_dedupe(liq, limit))
            _cache_put(key, response)
            return response

    results, source = [], "photon"
    try:
        results = [r for r in (_from_photon(f, bounds)
                               for f in _photon_search(expanded, limit, near=bias)) if r]
    except Exception:  # noqa: BLE001 - fall through to the backup geocoder
        results = []

    if not fast:
        # If nothing we got back actually contains the area the user named, resolve the area
        # first and search around it. This also covers Photon returning nothing usable:
        # "porur signal" comes back with a street in Ohio and a firm in New Zealand, both
        # correctly discarded, leaving an empty list for a perfectly ordinary Chennai query.
        best = max((relevance(expanded, r.label, r.context, r.category) for r in results),
                   default=0.0)
        if best < WEAK_MATCH:
            nearby = _anchored_retry(expanded, limit, bias, bounds)
            if nearby:
                source = "photon+anchor"
                results = nearby + results

        if not results:
            source = "nominatim"
            try:
                results = [r for r in (_from_nominatim(i, bounds)
                                       for i in _nominatim_search(expanded, limit)) if r]
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=502,
                                    detail="Address search is unavailable right now (%s)." % exc)

    response = GeocodeResponse(query=raw, expanded=expanded if expanded != raw else None,
                               source=source,
                               results=_dedupe(_rank(results, expanded), limit))
    _cache_put(key, response)
    return response


@router.get("/reverse")
async def reverse(lat: float, lng: float):
    """Label a dropped pin. Used for the scorecard heading and the PDF title, so it must
    return a human address, not an administrative path."""
    key = "r|%.5f|%.5f" % (lat, lng)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    label = None
    try:
        resp = httpx.get(PHOTON_REVERSE, params={"lat": lat, "lon": lng, "lang": "en"},
                         headers=HEADERS, timeout=8.0)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if features:
            primary, context = build_label(features[0].get("properties", {}))
            label = ", ".join(part for part in (primary, context) if part)
    except Exception:  # noqa: BLE001 - a missing label must never block a score
        label = None

    result = {"label": label}
    if label:
        _cache_put(key, result)
    return result
