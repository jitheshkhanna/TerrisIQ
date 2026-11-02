"""Composite scoring, grading and the H3 result cache."""
import datetime
import threading

import h3

from app.core import config as cfg
from app.engines.administrative import resolve_administrative
from app.engines.contamination import calculate_contamination_risk
from app.engines.crz import crz_screen
from app.engines.flood import calculate_flood_risk
from app.engines.scarcity import calculate_scarcity_risk

DISCLAIMER = (
    "This is a screening tool built on publicly available data from municipal "
    "corporations, CPCB, CGWB, NASA SRTM and OpenStreetMap. It does not constitute a "
    "professional environmental assessment. Verify all findings with a physical site "
    "visit and consult a qualified surveyor before making purchase decisions."
)

# Resolution 8 hexes are ~460 m edge. Two clicks inside one hex resolve to the same
# score, which is the right granularity given SRTM is 30 m.
H3_RESOLUTION = 8

_cache = {}
_cache_lock = threading.Lock()
CACHE_LIMIT = 5000

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

# Letter grades meant nothing to first-time users: "B" does not say whether to worry.
# The API keeps the letter for compatibility, but everything a person reads uses these.
VERDICT = {"A": "Very low risk", "B": "Low risk", "C": "Moderate risk",
           "D": "High risk", "F": "Very high risk"}
LEVEL = {"A": 1, "B": 2, "C": 3, "D": 4, "F": 5}

BASE_WEIGHTS = {
    "flood": cfg.WEIGHT_FLOOD,
    "contamination": cfg.WEIGHT_CONTAMINATION,
    "scarcity": cfg.WEIGHT_SCARCITY,
}

DEPTH_BLURB = {
    "deep": "A graded municipal flood survey backs this city, validated against "
            "recorded flooding.",
    "moderate": "This city publishes recorded flooding points and drains, but no graded "
                "flood survey. Terrain carries more of the score.",
    "baseline": "No municipal flood or groundwater survey is published for this city. "
                "The score comes from terrain and OpenStreetMap, and is a screening "
                "signal rather than a survey.",
}


def compute_grade(score):
    for ceiling, letter, band in cfg.GRADE_BANDS:
        if score <= ceiling:
            return letter, band
    return "F", "Critical Vulnerability"


def _band_for_grade(letter):
    for _, grade, band in cfg.GRADE_BANDS:
        if grade == letter:
            return band
    return "Critical Vulnerability"


def apply_severity_floor(grade, dimensions):
    """Stop one severe dimension from being averaged away by two mild ones."""
    worst_floor, trigger = None, None
    for label, block in dimensions:
        if block is None:
            continue
        for threshold, floor_grade in cfg.GRADE_FLOOR_RULES:
            if block["score"] >= threshold:
                if (worst_floor is None
                        or cfg.GRADE_SEVERITY[floor_grade] > cfg.GRADE_SEVERITY[worst_floor]):
                    worst_floor, trigger = floor_grade, (label, block["score"])
                break
    if worst_floor is None or cfg.GRADE_SEVERITY[grade] >= cfg.GRADE_SEVERITY[worst_floor]:
        return grade, _band_for_grade(grade), None
    reason = ("%s alone scores %d/100. Good drainage does not make contaminated "
              "groundwater safe to drink, so the overall reading is raised to %s rather "
              "than averaged down by the milder findings."
              % (trigger[0], trigger[1], VERDICT[worst_floor].lower()))
    return worst_floor, _band_for_grade(worst_floor), reason


def apply_evidence_ceiling(grade, city, flood, unavailable):
    """Stop thin data from reading as a clean bill of health.

    The severity floor stops one bad dimension being averaged away. This is its mirror:
    "A - Resilient" is a positive claim, and in a city with no graded flood survey and
    no groundwater evidence it is a claim about what nobody has measured. A plot can be
    genuinely fine and still not earn an A here; the grade is capped at B and the report
    says the cap is about the data, not the plot.
    """
    if cfg.GRADE_SEVERITY[grade] >= cfg.GRADE_SEVERITY["B"]:
        return grade, _band_for_grade(grade), None
    gaps = []
    if (flood or {}).get("basis") != "inundation_survey":
        gaps.append("no graded flood survey is published for %s" % city.name)
    if unavailable:
        gaps.append("%s cannot be scored here at all"
                    % " and ".join({"scarcity": "water scarcity",
                                    "contamination": "groundwater contamination",
                                    "flood": "flood"}[d] for d in unavailable))
    if not gaps:
        return grade, _band_for_grade(grade), None
    reason = ("Shown as low risk, not very low, because %s. That is about the data, "
              "not the plot: nothing here has been measured well enough to call it "
              "very low risk." % ", and ".join(gaps))
    return "B", _band_for_grade("B"), reason


def _summary(composite, grade, band, weighted):
    ranked = sorted(weighted, key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < 5:
        return ("%s (%d/100). No dimension shows a material risk signal in the "
                "available data." % (VERDICT[grade], composite))
    return ("%s (%d/100). The largest contributor is %s."
            % (VERDICT[grade], composite, ranked[0][2]))


def _decorate(raw):
    if raw is None:
        return None
    grade, band = compute_grade(raw["score"])
    out = dict(raw)
    out["grade"] = grade
    out["band"] = band
    out["verdict"] = VERDICT[grade]
    out["level"] = LEVEL[grade]
    return out


def assess(city, latitude, longitude, address=None, use_cache=True):
    cell = h3.latlng_to_cell(latitude, longitude, H3_RESOLUTION)
    key = "%s|%s" % (city.slug, cell)
    if use_cache:
        with _cache_lock:
            hit = _cache.get(key)
        if hit is not None:
            payload = dict(hit)
            payload.update({"latitude": latitude, "longitude": longitude,
                            "address": address, "cached": True})
            return payload

    flood = calculate_flood_risk(city, latitude, longitude)
    contamination = calculate_contamination_risk(city, latitude, longitude)
    scarcity = calculate_scarcity_risk(city, latitude, longitude)

    blocks = {"flood": flood, "contamination": contamination, "scarcity": scarcity}

    # A dimension with no data behind it is dropped and the remaining weights are
    # renormalised. Scoring it zero would quietly reward the city for publishing less.
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
    grade, band, ceiling_reason = apply_evidence_ceiling(grade, city, flood, unavailable)

    confidence = min([v["confidence"] for v in available.values()],
                     key=lambda c: CONFIDENCE_ORDER[c]) if available else "low"

    weighted = [(k, weights[k] * available[k]["score"],
                 {"flood": "monsoon flooding",
                  "contamination": "groundwater contamination",
                  "scarcity": "summer water scarcity"}[k]) for k in available]

    payload = {
        "city": city.to_dict(),
        "latitude": latitude,
        "longitude": longitude,
        "address": address,
        "administrative": resolve_administrative(city, latitude, longitude),
        "flood": _decorate(flood),
        "contamination": _decorate(contamination),
        "scarcity": _decorate(scarcity),
        "composite_score": composite,
        "composite_grade": grade,
        "composite_band": band,
        "verdict": VERDICT[grade],
        "level": LEVEL[grade],
        "unadjusted_grade": raw_grade,
        "grade_floor_applied": floor_reason is not None,
        "grade_floor_reason": floor_reason,
        "severity_note": floor_reason,
        "evidence_ceiling_applied": ceiling_reason is not None,
        "evidence_ceiling_reason": ceiling_reason,
        "confidence": confidence,
        "summary": _summary(composite, grade, band, weighted),
        "weights": {k: round(v, 3) for k, v in weights.items()},
        "base_weights": BASE_WEIGHTS,
        "unavailable_dimensions": unavailable,
        "crz": crz_screen(city, latitude, longitude),
        "coverage_note": DEPTH_BLURB.get(city.depth),
        "h3_cell": cell,
        "cached": False,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                 .replace(microsecond=0).isoformat(),
        "disclaimer": DISCLAIMER,
    }

    with _cache_lock:
        if len(_cache) >= CACHE_LIMIT:
            _cache.clear()
        _cache[key] = payload
    return payload
