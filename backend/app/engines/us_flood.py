"""US flood risk from FEMA's open National Flood Hazard Layer (NFHL).

No data is bundled or scraped: we query FEMA's public ArcGIS REST service per point, the
same primary source commercial tools stand on. Screening-grade: it reads the mapped SFHA
zone, not a modelled depth. Returns the same RiskScore shape the India engines produce, so
the existing ScoreCard renders it unchanged.

Note: FEMA's endpoint may refuse non-US IPs; verify reachability from the deployed (US)
backend, not from local dev abroad.
"""
import datetime

import httpx

from app.core import config as cfg
from app.core.scoring import (BASE_WEIGHTS, CONFIDENCE_ORDER, DISCLAIMER, LEVEL, VERDICT,
                              apply_severity_floor, compute_grade)
from app.engines import universal
from app.engines.common import ScoreBuilder
from app.engines.common import haversine_m

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
# EPA ECHO geographic facility search (keyless JSON). Authoritative, but a proximity screen,
# not a plume model. Like FEMA's service it may refuse non-US IPs — verify on the US deploy.
ECHO = "https://echodata.epa.gov/echo/echo_rest_services.get_facility_info"
_BANDS = {g: b for _, g, b in cfg.GRADE_BANDS}

# Representative score inside each grade band (A<=20, B<=40, C<=60, D<=80, F<=100).
_LEVEL_SCORE = {1: 10, 2: 32, 3: 50, 4: 72, 5: 90}


def _classify(zone, subty):
    """FEMA zone -> (level 1..5, one-line fact). SFHA (1% annual) is high; V/VE add coastal
    wave velocity; shaded X (0.2% annual) is moderate; unshaded X minimal; D undetermined."""
    zone = (zone or "").upper().strip()
    subty = (subty or "").upper()
    if zone in ("V", "VE", "VO"):
        return 5, "In a coastal high-velocity flood zone"
    if zone in ("A", "AE", "AH", "AO", "AR", "A99"):
        return 4, "In a FEMA 1% annual-chance flood zone (SFHA)"
    if "0.2 PCT" in subty:
        return 3, "In the 0.2% annual-chance (500-year) floodplain"
    if zone == "D":
        return 2, "Flood risk undetermined; this area is unstudied"
    # Zone X (unshaded) and anything else mapped as minimal.
    return 1, "Outside FEMA's mapped flood hazard area"


def _score_from_attrs(attrs):
    """attrs: list of FEMA feature attribute dicts. Returns a RiskScore dict, or None when
    the point intersects no mapped flood polygon. Pure (no network) so it is unit-testable."""
    if not attrs:
        return None
    level, fact = max((_classify(a.get("FLD_ZONE"), a.get("ZONE_SUBTY")) for a in attrs),
                      key=lambda lf: lf[0])
    score = _LEVEL_SCORE[level]
    grade, band = compute_grade(score)
    fact_level = "high" if level >= 4 else "good" if level == 1 else "medium"
    return {
        "score": score, "grade": grade, "band": band, "verdict": VERDICT[grade],
        "level": level, "basis": "fema_nfhl", "confidence": "high", "warnings": [],
        "facts": [{"text": fact, "level": fact_level}],
        "components": [], "details": {"source": "FEMA NFHL",
                                      "zones": sorted({(a.get("FLD_ZONE") or "").upper()
                                                       for a in attrs if a.get("FLD_ZONE")})},
    }


def _unmapped(note):
    # A placeholder flood block carrying only the reason FEMA gave nothing. us_assess detects
    # this basis ("fema_unmapped") and replaces it with the terrain baseline, so this low
    # score is never what the user actually sees — it just flags "no FEMA mapping here".
    grade, band = compute_grade(_LEVEL_SCORE[1])
    return {
        "score": _LEVEL_SCORE[1], "grade": grade, "band": band, "verdict": VERDICT[grade],
        "level": 1, "basis": "fema_unmapped", "confidence": "low", "warnings": [note],
        "facts": [{"text": note, "level": "info"}], "components": [],
        "details": {"source": "FEMA NFHL", "zones": []},
    }


def fema_flood(lat, lng, timeout=12.0):
    """RiskScore-shaped dict for a US point. Never raises: a FEMA outage or an unmapped area
    returns a low-confidence result with a note, so a dropped service never destroys a read.
    FEMA's ArcGIS is slow/throttly on cold bursts, so retry once before giving up."""
    params = {"geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": "4326",
              "spatialRel": "esriSpatialRelIntersects",
              "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF", "returnGeometry": "false", "f": "json"}
    for _ in range(2):
        try:
            resp = httpx.get(NFHL, params=params, timeout=timeout)
            attrs = [f["attributes"] for f in resp.json().get("features", [])]
        except Exception:
            continue
        return _score_from_attrs(attrs) or _unmapped("Outside FEMA's mapped flood area; risk unknown here")
    return _unmapped("FEMA flood service is unreachable right now")


# CONUS + Alaska + Hawaii, coarse bbox routing (not a precise border test; good enough to
# send a point to FEMA vs the India engines).
def in_us(lat, lng):
    return ((24.0 <= lat <= 49.5 and -125.0 <= lng <= -66.5)
            or (51.0 <= lat <= 71.5 and -170.0 <= lng <= -129.0)
            or (18.0 <= lat <= 23.0 and -161.0 <= lng <= -154.0))


def _km(m):
    return "%d m" % int(round(m, -1)) if m < 1000 else "%.1f km" % (m / 1000.0)


def _epa_score(facilities, lat, lng):
    """Pure (no network): an EPA ECHO facility list -> a contamination RiskScore dict. A
    regulated facility with a current violation nearby is the signal; everything is a
    proximity screen, labelled as such, so it never reads as a soil or groundwater test."""
    sb = ScoreBuilder("contamination")
    sb.downgrade("medium")
    nearest = None        # (distance_m, name)
    nearest_vio = None    # (distance_m, name) for a facility with current violations
    count = vio_count = 0
    for f in facilities:
        try:
            flat, flng = float(f.get("FacLat")), float(f.get("FacLong"))
        except (TypeError, ValueError):
            continue
        d = haversine_m(lat, lng, flat, flng)
        count += 1
        name = f.get("FacName") or "an EPA-registered facility"
        if nearest is None or d < nearest[0]:
            nearest = (d, name)
        if str(f.get("CurrVioFlag") or "").upper() in ("Y", "YES", "TRUE"):
            vio_count += 1
            if nearest_vio is None or d < nearest_vio[0]:
                nearest_vio = (d, name)

    if count == 0:
        sb.fact("No EPA facilities nearby", "info")
        sb.warn("No EPA-registered facilities are mapped within ~5 km. This is a proximity "
                "screen against EPA's ECHO database, not a soil or groundwater test.")
        sb.add("epa_proximity", 0.0, "No EPA-registered facilities within range")
        return sb.build()

    if nearest_vio and nearest_vio[0] < 800:
        pts, lvl, who = 45.0, "high", nearest_vio
        sb.warn("%s, with a current EPA violation on record, is %s away."
                % (who[1], _km(who[0])))
    elif nearest_vio and nearest_vio[0] < 3000:
        pts, lvl, who = 28.0, "medium", nearest_vio
        sb.warn("%s, with a current EPA violation on record, is %s away."
                % (who[1], _km(who[0])))
    elif nearest[0] < 800:
        pts, lvl, who = 18.0, "medium", nearest
    elif nearest[0] < 3000:
        pts, lvl, who = 8.0, "low", nearest
    else:
        pts, lvl, who = 0.0, None, nearest
    if lvl:
        sb.fact("Regulated facility %s away" % _km(who[0]), lvl)
    sb.add("epa_proximity", pts,
           "EPA ECHO: %d regulated facilities within ~5 km, %d with current violations; "
           "nearest is %s away" % (count, vio_count, _km(nearest[0])),
           facilities=count, with_violations=vio_count, nearest_m=int(nearest[0]))
    return sb.build()


def epa_contamination(lat, lng, timeout=4.5):
    """Contamination RiskScore for a US point from EPA ECHO within ~3 miles. Never raises;
    returns None when the service is unreachable, so the dimension is dropped and the
    evidence ceiling labels the gap rather than a fabricated clean reading."""
    params = {"output": "JSON", "p_lat": lat, "p_long": lng, "p_radius": 3, "responseset": 100}
    for _ in range(2):
        try:
            resp = httpx.get(ECHO, params=params, timeout=timeout)
            facs = ((resp.json().get("Results") or {}).get("Facilities")) or []
        except Exception:  # noqa: BLE001 - a dropped service must never destroy a read
            continue
        return _epa_score(facs, lat, lng)
    return None


def _decorate(block):
    if block is None:
        return None
    grade, band = compute_grade(block["score"])
    out = dict(block)
    out.update({"grade": grade, "band": band, "verdict": VERDICT[grade], "level": LEVEL[grade]})
    return out


def us_assess(lat, lng, address=None):
    """Full /risk payload for a US point: FEMA flood (a graded hazard layer) + EPA ECHO
    contamination, composited and renormalised. Water scarcity is not yet scored for the US
    and is dropped-and-labelled, not zeroed. Same shape the India engines produce."""
    flood = fema_flood(lat, lng)
    if flood.get("basis") == "fema_unmapped":
        # FEMA has no usable mapping here (unmapped county, or the service is down). Do NOT
        # let that read as grade A "very low risk" — score the point on the terrain baseline
        # instead, and keep the FEMA note so the gap is explicit. (Guardrail: thin data is
        # never silently "safe"; a dropped source falls back to terrain, not to zero hazard.)
        fema_note = flood["warnings"][0] if flood.get("warnings") else "FEMA mapping unavailable here"
        flood = universal.flood_baseline(lat, lng)
        flood.setdefault("warnings", []).insert(0, fema_note)
        flood["details"]["fema"] = fema_note
    contamination = epa_contamination(lat, lng)
    blocks = {"flood": flood, "contamination": contamination, "scarcity": None}
    available = {k: v for k, v in blocks.items() if v is not None}
    total = sum(BASE_WEIGHTS[k] for k in available) or 1.0
    weights = {k: BASE_WEIGHTS[k] / total for k in available}

    composite = int(round(sum(weights[k] * available[k]["score"] for k in available)))
    composite = max(0, min(100, composite))
    raw_grade, _ = compute_grade(composite)
    labels = {"flood": "Flood", "contamination": "Groundwater contamination"}
    grade, band, floor_reason = apply_severity_floor(
        raw_grade, [(labels[k], v) for k, v in available.items()])

    # US-specific evidence ceiling: FEMA NFHL IS a graded flood survey, so (unlike the India
    # engine) we do not claim "no flood survey". We only cap a very-low grade when a whole
    # dimension is missing, and say which.
    unavailable = [k for k in BASE_WEIGHTS if k not in available]
    ceiling_reason = None
    if cfg.GRADE_SEVERITY[grade] < cfg.GRADE_SEVERITY["B"] and unavailable:
        pretty = {"contamination": "groundwater contamination", "scarcity": "water scarcity"}
        grade, band = "B", _BANDS["B"]
        ceiling_reason = ("Shown as low risk, not very low, because %s %s not yet scored for "
                          "US locations. That is about the data, not the plot."
                          % (" and ".join(pretty[d] for d in unavailable),
                             "is" if len(unavailable) == 1 else "are"))

    confidence = min([v["confidence"] for v in available.values()],
                     key=lambda c: CONFIDENCE_ORDER[c]) if available else "low"
    city = {"slug": "us", "name": "United States", "state": "", "corporation": "FEMA NFHL + EPA ECHO",
            "centre": {"lat": lat, "lng": lng},
            "bbox": {"lat_min": 24.0, "lat_max": 49.5, "lng_min": -125.0, "lng_max": -66.5},
            "depth": "deep", "layers": ["fema_flood", "epa_echo"],
            "scoreable_dimensions": list(available),
            "ward_label": "Zone", "zone_label": "Zone", "notes": {}}
    admin = {"summary": address or "United States", "inside_gcc": True,
             "ward_is_official": True, "city": "us", "city_name": "United States"}
    return {
        "city": city, "latitude": lat, "longitude": lng, "address": address,
        "administrative": admin,
        "flood": _decorate(flood), "contamination": _decorate(contamination), "scarcity": None,
        "composite_score": composite, "composite_grade": grade, "composite_band": band,
        "verdict": VERDICT[grade], "level": LEVEL[grade], "unadjusted_grade": raw_grade,
        "grade_floor_applied": floor_reason is not None, "grade_floor_reason": floor_reason,
        "severity_note": floor_reason,
        "evidence_ceiling_applied": ceiling_reason is not None,
        "evidence_ceiling_reason": ceiling_reason, "confidence": confidence,
        "summary": ("%s (%d/100). Flood from %s; contamination from EPA's ECHO facility "
                    "database. Water scarcity is not yet scored for US locations."
                    % (VERDICT[grade], composite,
                       "a terrain baseline (FEMA mapping was unavailable here)"
                       if flood.get("basis") == "terrain_and_proxies"
                       else "FEMA's National Flood Hazard Layer")),
        "weights": {k: round(v, 3) for k, v in weights.items()}, "base_weights": BASE_WEIGHTS,
        "unavailable_dimensions": unavailable,
        "crz": None,
        "coverage_note": "US coverage: FEMA NFHL flood + EPA ECHO contamination. Water "
                         "scarcity not yet scored.",
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                .replace(microsecond=0).isoformat(),
        "disclaimer": DISCLAIMER,
    }


if __name__ == "__main__":
    # Offline checks on the pure logic (no network needed).
    assert _classify("VE", "")[0] == 5
    assert _classify("AE", "")[0] == 4
    assert _classify("A", "")[0] == 4
    assert _classify("X", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD")[0] == 3
    assert _classify("X", "")[0] == 1
    assert _classify("D", "")[0] == 2
    assert _score_from_attrs([]) is None
    worst = _score_from_attrs([{"FLD_ZONE": "X"}, {"FLD_ZONE": "AE"}])
    assert worst["level"] == 4 and worst["grade"] == "D", worst
    assert _score_from_attrs([{"FLD_ZONE": "X"}])["level"] == 1
    assert _unmapped("x")["confidence"] == "low"
    # EPA contamination scoring (pure).
    none_near = _epa_score([], 29.76, -95.36)
    assert none_near["score"] == 0 and any(f["level"] == "info" for f in none_near["facts"]), none_near
    violator = _epa_score([{"FacLat": 29.761, "FacLong": -95.361, "FacName": "Acme Plating",
                            "CurrVioFlag": "Y"}], 29.76, -95.36)
    assert violator["score"] >= 40, violator  # a nearby current violator is a real signal
    compliant_far = _epa_score([{"FacLat": 29.80, "FacLong": -95.40, "FacName": "Depot",
                                 "CurrVioFlag": "N"}], 29.76, -95.36)
    assert 0 <= compliant_far["score"] <= 10, compliant_far
    print("offline logic OK")
    # Live probe (best-effort; FEMA may refuse non-US IPs).
    try:
        print("Miami Beach ->", fema_flood(25.7907, -80.1300))
    except Exception as e:
        print("live FEMA probe failed (verify on US deploy):", e)
