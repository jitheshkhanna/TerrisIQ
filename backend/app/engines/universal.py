"""Universal BASELINE risk for any point outside a surveyed city.

No bundled municipal layers exist outside the eight covered cities, so this engine scores
from signals available anywhere on Earth: global SRTM terrain (relative + catchment
elevation, already fetched by `elevation_profile`) and live OpenStreetMap hydrology /
industrial proximity via the Overpass API.

It returns the exact RiskResponse shape the city engines produce, so the frontend and PDF
render it unchanged — but always labelled `depth="baseline"`, low/medium confidence, and
fail-soft: if Overpass is unreachable the flood score falls back to terrain alone with a
"source temporarily unreachable" note, and water scarcity / contamination stay explicitly
unscored rather than being filled with a reassuring zero. Thin data never reads as "safe".
"""
import datetime

import httpx

from app.core import config as cfg
from app.core.elevation import elevation_profile
from app.core.scoring import (BASE_WEIGHTS, CONFIDENCE_ORDER, DISCLAIMER, LEVEL, VERDICT,
                              apply_evidence_ceiling, apply_severity_floor, compute_grade)
from app.engines import india_hazards
from app.engines.common import ScoreBuilder, haversine_m

# Public Overpass mirrors, tried in order. Each call is short-timed; the whole thing is
# best-effort, so all three failing just means terrain-only with an honest note.
_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]
_HYDRO_RADIUS_M = 1500
_COAST_RADIUS_M = 2500


def _element_point(el):
    """A representative (lat, lon) for an Overpass element: node coords, or way/relation
    center (requested with `out center`). None when neither is present."""
    if el.get("type") == "node" and "lat" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    if c:
        return c["lat"], c["lon"]
    return None


def _classify(el):
    """Which hydrology/industrial category an element falls in, or None to ignore."""
    t = el.get("tags", {})
    if t.get("natural") == "coastline":
        return "coast"
    if t.get("waterway") in ("drain", "ditch", "canal") or t.get("man_made") == "drain":
        return "drain"
    if t.get("natural") == "water" or t.get("water") or t.get("waterway") in ("river", "stream", "riverbank"):
        return "water"
    if t.get("landuse") == "industrial" or t.get("man_made") in ("works", "wastewater_plant"):
        return "industrial"
    return None


def _overpass(lat, lon, timeout=4.5):
    """Nearest water / drain / industrial / coastline to the point, by metric distance.

    Returns {"available": bool, <category>: {"m": int, "name": str|None}, ...}. Never raises:
    every mirror failing yields {"available": False}, which the callers treat as a data gap.
    """
    query = (
        "[out:json][timeout:20];("
        "nwr(around:%d,%f,%f)[natural=water];"
        "nwr(around:%d,%f,%f)[waterway];"
        "nwr(around:%d,%f,%f)[landuse=industrial];"
        "nwr(around:%d,%f,%f)[man_made~\"drain|works|wastewater_plant\"];"
        "way(around:%d,%f,%f)[natural=coastline];"
        ");out center tags;"
        % (_HYDRO_RADIUS_M, lat, lon, _HYDRO_RADIUS_M, lat, lon, _HYDRO_RADIUS_M, lat, lon,
           _HYDRO_RADIUS_M, lat, lon, _COAST_RADIUS_M, lat, lon)
    )
    elements = None
    for url in _OVERPASS_MIRRORS:
        try:
            resp = httpx.post(url, data={"data": query}, timeout=timeout)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            break
        except Exception:  # noqa: BLE001 - try the next mirror, then fall back to terrain-only
            continue
    if elements is None:
        return {"available": False}

    nearest = {}
    for el in elements:
        cat = _classify(el)
        if cat is None:
            continue
        pt = _element_point(el)
        if pt is None:
            continue
        d = haversine_m(lat, lon, pt[0], pt[1])
        if cat not in nearest or d < nearest[cat]["m"]:
            nearest[cat] = {"m": int(round(d)), "name": el.get("tags", {}).get("name")}
    nearest["available"] = True
    return nearest


def _dist(m):
    return "%d m" % int(round(m, -1)) if m < 1000 else "%.1f km" % (m / 1000.0)


def _flood(lat, lon, hydro):
    """Terrain + live OSM hydrology flood baseline. Mirrors the no-survey branch of the
    Chennai engine so scores stay comparable across the covered/uncovered boundary."""
    sb = ScoreBuilder("flood")
    sb.fact("No flood survey here", "info")
    sb.warn("No graded flood survey is published for this area. The score comes from "
            "terrain and OpenStreetMap water — a screening signal, not a survey.")
    sb.downgrade("low")

    # Terrain: catchment-relative elevation is the strongest uniform flood signal.
    profile = elevation_profile(lat, lon)
    sb.details["elevation"] = profile
    p = cfg.NO_SURVEY_POINTS
    if profile.get("available") and profile.get("relative_m") is not None:
        wide = profile.get("relative_catchment_m")
        basin = wide if wide is not None else profile["relative_m"]
        if basin <= -4.0:
            pts = p["elevation_hollow"]
        elif basin <= -2.0:
            pts = p["elevation_dip"]
        elif basin <= -0.5:
            pts = p["elevation_slight"]
        elif basin >= 6.0:
            pts = p["elevation_rise"]
        else:
            pts = 0.0
        if basin <= -2.0:
            sb.fact("%.1f m below catchment" % abs(basin), "high" if basin <= -4.0 else "medium")
            sb.warn("The plot sits %.1fm below the surrounding catchment, so rainfall from "
                    "a wide area drains toward it." % abs(basin))
        elif basin >= 6.0:
            sb.fact("Sits on higher ground", "good")
        sb.add("elevation", pts,
               "Elevation %.0fm; %+.1fm vs the 1 km catchment"
               % (profile["elevation_m"], basin),
               elevation_m=profile["elevation_m"], relative_catchment_m=wide)
    else:
        sb.warn("The elevation service did not answer, so terrain is missing from this score.")
        sb.downgrade("medium")

    # Live OSM water proximity.
    if hydro.get("available"):
        water = hydro.get("water")
        if water:
            m = water["m"]
            name = water["name"] or "an unnamed water body"
            if m < cfg.WATERBODY_VERY_NEAR_M:
                pts = p["water_very_near"]
                sb.fact("Water %s away" % _dist(m), "high" if m < 50 else "medium")
                sb.warn("%s runs %s away. Expect backflow and bank overtopping in heavy rain."
                        % (name[:1].upper() + name[1:], _dist(m)))
            elif m < cfg.WATERBODY_NEAR_M:
                pts = p["water_near"]
            elif m < cfg.WATERBODY_MID_M:
                pts = p["water_mid"]
            else:
                pts = 0.0
            sb.add("waterbody", pts, "Nearest water (%s) is %s away" % (name, _dist(m)),
                   nearest_waterbody_m=m, name=name)
        coast = hydro.get("coast")
        if coast:
            sb.details["coast"] = {"nearest_coast_m": coast["m"]}
    else:
        sb.fact("Water map unavailable", "info")
        sb.warn("The OpenStreetMap water service was temporarily unreachable, so this score "
                "rests on terrain alone — not a sign the area is dry.")

    result = sb.build()
    result["basis"] = "terrain_and_proxies"
    return result


def _contamination(hydro, cepi):
    """Contamination for an uncovered point. A CPCB CEPI cluster match is the authoritative
    MODERATE signal; absent that, OSM industrial proximity is a weak BASELINE proxy. Returns
    None only when there is neither a cluster nor a reachable OSM map (dimension dropped and
    labelled, never a silent zero)."""
    if cepi is not None:
        sb = ScoreBuilder("contamination")
        sb.downgrade("medium")  # authoritative classification, but regional/proximity not a plume
        base = cfg.CLUSTER_LEVEL_POINTS[cepi["level"]]
        d, radius = cepi["distance_m"], cepi["radius_m"]
        if d <= radius:
            pts = base
        else:
            pts = base * max(0.0, 1.0 - (d - radius) / cfg.CLUSTER_DECAY_M)
        pretty = cepi["level"].replace("_", " ")
        sb.fact("CPCB %s cluster" % pretty, "high" if d <= radius else "medium")
        sb.warn("%s is a CPCB CEPI %s industrial cluster; the point is %s from it. Groundwater "
                "and soil contamination are documented here — test before relying on a borewell."
                % (cepi["name"], pretty, _dist(d)))
        sb.add("cepi_cluster", pts,
               "Inside/near the %s CPCB %s cluster (%s away)" % (cepi["name"], pretty, _dist(d)),
               cluster=cepi["name"], level=cepi["level"], distance_m=d)
        out = sb.build()
        out["basis"] = "cpcb_cepi"
        return out

    if not hydro.get("available"):
        return None
    sb = ScoreBuilder("contamination")
    sb.downgrade("low")
    ind = hydro.get("industrial")
    if ind:
        m = ind["m"]
        near, mid, far = cfg.OSM_INDUSTRIAL_POINTS
        if m < cfg.OSM_INDUSTRIAL_NEAR_M:
            pts, lvl = near, "high"
        elif m < cfg.OSM_INDUSTRIAL_MID_M:
            pts, lvl = mid, "medium"
        elif m < cfg.OSM_INDUSTRIAL_FAR_M:
            pts, lvl = far, "low"
        else:
            pts, lvl = 0.0, None
        if lvl:
            sb.fact("Industrial land %s away" % _dist(m), lvl)
            sb.warn("OpenStreetMap maps industrial land %s away. This is a proximity proxy, "
                    "not a CPCB pollution assessment — verify groundwater quality locally."
                    % _dist(m))
        sb.add("osm_industrial", pts, "Nearest mapped industrial land is %s away" % _dist(m),
               nearest_industrial_m=m)
    else:
        sb.fact("No CPCB cluster match", "info")
        sb.warn("No authoritative CPCB polluted-cluster data is matched for this area, and "
                "no industrial land is mapped nearby in OpenStreetMap. Absence of mapping is "
                "not a clean bill of health.")
    return sb.build()


_CGWB_POINTS = {"overexploited": cfg.FIRKA_POINTS["overexploited"],
                "critical": cfg.FIRKA_POINTS["critical"],
                "semi_critical": cfg.FIRKA_POINTS["semi_critical"],
                "safe": cfg.FIRKA_POINTS["safe"]}


def _scarcity(state):
    """Water scarcity from the CGWB regional (state-level) groundwater category. A regional
    finding, not a local block measurement, so it is low-confidence and says so. None when
    the state is not in the index (dimension dropped, not guessed)."""
    cls = india_hazards.cgwb_status(state)
    if cls is None:
        return None
    sb = ScoreBuilder("scarcity")
    sb.downgrade("low")
    pretty = cls.replace("_", "-")
    if cls in ("overexploited", "critical"):
        sb.fact("CGWB: %s groundwater" % pretty, "medium")
        sb.warn("CGWB classifies %s groundwater as '%s' at the regional level. Expect borewell "
                "yields to fall in summer; confirm the local block category and a neighbour's "
                "borewell depth before relying on a well." % (state, pretty))
    elif cls == "semi_critical":
        sb.fact("CGWB: semi-critical groundwater", "low")
    else:
        sb.fact("CGWB: safe groundwater (regional)", "good")
    sb.add("cgwb_region", _CGWB_POINTS[cls],
           "CGWB regional groundwater category for %s: %s" % (state, pretty),
           classification=cls, provenance="cgwb_regional")
    out = sb.build()
    out["basis"] = "cgwb_regional"
    return out


def _decorate(block):
    if block is None:
        return None
    grade, band = compute_grade(block["score"])
    out = dict(block)
    out.update({"grade": grade, "band": band, "verdict": VERDICT[grade], "level": LEVEL[grade]})
    return out


class _Region:
    """Minimal city-like object so the shared evidence-ceiling helper can name the place."""
    def __init__(self, name):
        self.name = name


def assess_universal(lat, lng, address, region):
    """Full /risk payload for any Indian point outside a covered city. Same shape as
    `scoring.assess`, tier BASELINE, fully fail-soft."""
    hydro = _overpass(lat, lng)
    cepi = india_hazards.nearest_cepi(lat, lng)
    flood = _flood(lat, lng, hydro)
    contamination = _contamination(hydro, cepi)
    scarcity = _scarcity(region.get("state"))

    blocks = {"flood": flood, "contamination": contamination, "scarcity": scarcity}
    available = {k: v for k, v in blocks.items() if v is not None}
    total_weight = sum(BASE_WEIGHTS[k] for k in available) or 1.0
    weights = {k: BASE_WEIGHTS[k] / total_weight for k in available}

    composite = int(round(sum(weights[k] * available[k]["score"] for k in available)))
    composite = max(0, min(100, composite))
    raw_grade, _ = compute_grade(composite)

    labels = {"flood": "Flood", "contamination": "Groundwater contamination",
              "scarcity": "Water scarcity"}
    grade, band, floor_reason = apply_severity_floor(
        raw_grade, [(labels[k], v) for k, v in available.items()])
    unavailable = [k for k in BASE_WEIGHTS if k not in available]
    grade, band, ceiling_reason = apply_evidence_ceiling(grade, _Region(region["name"]),
                                                         flood, unavailable)

    confidence = min([v["confidence"] for v in available.values()],
                     key=lambda c: CONFIDENCE_ORDER[c]) if available else "low"

    name = region.get("name") or "This location"
    parts = []
    for x in (region.get("locality"), region.get("district"), region.get("state")):
        if x and x not in parts:  # Photon often repeats the name as locality and district
            parts.append(x)
    place = ", ".join(parts) or name
    # A match against a national dataset (CPCB CEPI / CGWB regional) lifts the point from a
    # pure-terrain BASELINE to MODERATE; the authoritative source is named for provenance.
    authoritative = []
    if cepi is not None:
        authoritative.append("CPCB CEPI (%s)" % cepi["name"])
    if scarcity is not None:
        authoritative.append("CGWB regional groundwater")
    tier = "moderate" if authoritative else "baseline"
    corporation = (" + ".join(authoritative) + " + terrain/OpenStreetMap" if authoritative
                   else "Terrain + OpenStreetMap baseline")
    city = {
        "slug": "in-baseline", "name": name, "state": region.get("state") or "India",
        "corporation": corporation,
        "centre": {"lat": lat, "lng": lng},
        "bbox": {"lat_min": lat - 0.05, "lng_min": lng - 0.05,
                 "lat_max": lat + 0.05, "lng_max": lng + 0.05},
        "depth": tier, "layers": [], "scoreable_dimensions": list(available),
        "ward_label": "Area", "zone_label": "District", "notes": {},
    }
    admin = {"summary": place, "inside_gcc": False, "ward_is_official": False,
             "city": "in-baseline", "city_name": name, "ward": region.get("district"),
             "zone": region.get("state")}

    return {
        "city": city, "latitude": lat, "longitude": lng, "address": address,
        "administrative": admin,
        "flood": _decorate(flood), "contamination": _decorate(contamination),
        "scarcity": _decorate(scarcity),
        "composite_score": composite, "composite_grade": grade, "composite_band": band,
        "verdict": VERDICT[grade], "level": LEVEL[grade], "unadjusted_grade": raw_grade,
        "grade_floor_applied": floor_reason is not None, "grade_floor_reason": floor_reason,
        "severity_note": floor_reason,
        "evidence_ceiling_applied": ceiling_reason is not None,
        "evidence_ceiling_reason": ceiling_reason,
        "confidence": confidence,
        "summary": ("%s (%d/100). Screening read for %s from terrain, OpenStreetMap%s. No "
                    "municipal survey covers this area, so treat it as a first read, not a "
                    "verdict." % (VERDICT[grade], composite, place,
                                  " and " + ", ".join(authoritative) if authoritative else "")),
        "weights": {k: round(v, 3) for k, v in weights.items()}, "base_weights": BASE_WEIGHTS,
        "unavailable_dimensions": unavailable,
        "crz": None,
        "coverage_note": (("No municipal survey covers this point. Flood comes from global "
                           "terrain (SRTM) + OpenStreetMap; %s add national context. A "
                           "screening read, not a local survey." % ", ".join(authoritative))
                          if authoritative else
                          ("No municipal flood or groundwater survey is published here. The "
                           "score comes from global terrain (SRTM) and OpenStreetMap, and is a "
                           "screening signal rather than a survey.")),
        "h3_cell": None, "cached": False,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                 .replace(microsecond=0).isoformat(),
        "disclaimer": DISCLAIMER,
    }


if __name__ == "__main__":
    # Offline checks on the pure logic (no network).
    assert 425 < haversine_m(13.0, 80.0, 13.0, 80.004) < 440, haversine_m(13.0, 80.0, 13.0, 80.004)
    assert _classify({"tags": {"natural": "coastline"}}) == "coast"
    assert _classify({"tags": {"waterway": "drain"}}) == "drain"
    assert _classify({"tags": {"natural": "water"}}) == "water"
    assert _classify({"tags": {"landuse": "industrial"}}) == "industrial"
    assert _classify({"tags": {"highway": "residential"}}) is None
    # A deep hollow with water on the doorstep must score as a real flood signal, not zero.
    # Patch the module-local name the engine actually calls, so no network is touched.
    globals()["elevation_profile"] = lambda a, b: {"available": True, "elevation_m": 4.0,
                                                   "relative_m": -1.0, "relative_catchment_m": -4.5}
    hydro = {"available": True, "water": {"m": 30, "name": "Buckingham Canal"}}
    blk = _flood(13.09, 80.28, hydro)
    assert blk["score"] >= 40 and blk["confidence"] == "low", blk
    # Overpass down -> terrain-only, explicit gap, never a silent safe zero.
    blk2 = _flood(13.09, 80.28, {"available": False})
    assert any(f["level"] == "info" for f in blk2["facts"]), blk2
    print("universal offline logic OK")
