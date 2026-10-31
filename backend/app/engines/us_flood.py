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

from app.core.scoring import BASE_WEIGHTS, DISCLAIMER, LEVEL, VERDICT, compute_grade

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"

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
    # shortcut: 'unknown' is scored low with low confidence; a proper evidence-ceiling (like
    # the India engine's) should cap any composite when FEMA has no coverage. Add when US
    # gets more than one peril.
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


def us_assess(lat, lng, address=None):
    """Full /risk payload for a US point: FEMA flood only for now, other dimensions absent
    and labelled, so the existing ScoreCard renders it with no UI change."""
    flood = fema_flood(lat, lng)
    grade = flood["grade"]
    city = {"slug": "us", "name": "United States", "state": "", "corporation": "FEMA NFHL",
            "centre": {"lat": lat, "lng": lng},
            "bbox": {"lat_min": 24.0, "lat_max": 49.5, "lng_min": -125.0, "lng_max": -66.5},
            "depth": "moderate", "layers": ["fema_flood"], "scoreable_dimensions": ["flood"],
            "ward_label": "Zone", "zone_label": "Zone", "notes": {}}
    admin = {"summary": address or "United States", "inside_gcc": True,
             "ward_is_official": True, "city": "us", "city_name": "United States"}
    return {
        "city": city, "latitude": lat, "longitude": lng, "address": address,
        "administrative": admin, "flood": flood, "contamination": None, "scarcity": None,
        "composite_score": flood["score"], "composite_grade": grade,
        "composite_band": flood["band"], "verdict": VERDICT[grade], "level": LEVEL[grade],
        "unadjusted_grade": grade, "confidence": flood["confidence"],
        "summary": "Flood screening from FEMA's National Flood Hazard Layer. Groundwater and "
                   "water-scarcity data are not yet available for US locations.",
        "weights": {"flood": 1.0}, "base_weights": BASE_WEIGHTS,
        "unavailable_dimensions": ["contamination", "scarcity"],
        "coverage_note": "US coverage is flood-only for now, from FEMA's NFHL.",
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
    print("offline logic OK")
    # Live probe (best-effort; FEMA may refuse non-US IPs).
    try:
        print("Miami Beach ->", fema_flood(25.7907, -80.1300))
    except Exception as e:
        print("live FEMA probe failed (verify on US deploy):", e)
