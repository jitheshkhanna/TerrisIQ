"""Lookups against the bundled, cited national hazard index (see data/india_national_hazards.json).

These raise an uncovered Indian point from the pure-terrain BASELINE to the MODERATE tier
where an authoritative national dataset matches: a CPCB CEPI polluted cluster (contamination),
a CGWB regional groundwater category (scarcity), or an AAI/airport obstacle funnel (a Build
Scope NOC trigger). Everything is a cited regional/proximity screen, never a precise local
measurement, and nothing here is fabricated — absence of a match returns None, not a guess.
"""
import json
import os

from app.engines.common import haversine_m

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "data", "india_national_hazards.json")
_data = None


def _load():
    global _data
    if _data is None:
        with open(_PATH) as fh:
            _data = json.load(fh)
    return _data


def nearest_cepi(lat, lng):
    """Nearest CPCB CEPI cluster whose (radius + a 2.5 km decay skirt) contains the point.
    Returns {name, state, level, distance_m, radius_m} or None."""
    best = None
    for c in _load().get("cepi_clusters", []):
        d = haversine_m(lat, lng, c["lat"], c["lng"])
        if d <= c["radius_m"] + 2500 and (best is None or d < best["distance_m"]):
            best = {"name": c["name"], "state": c["state"], "level": c["level"],
                    "distance_m": int(round(d)), "radius_m": c["radius_m"]}
    return best


def nearest_airport(lat, lng):
    """Nearest aerodrome whose approximate AAI obstacle funnel contains the point.
    Returns {name, kind, distance_m, funnel_km} or None."""
    best = None
    for a in _load().get("airports", []):
        d = haversine_m(lat, lng, a["lat"], a["lng"])
        if d <= a["funnel_km"] * 1000 and (best is None or d < best["distance_m"]):
            best = {"name": a["name"], "kind": a["kind"], "distance_m": int(round(d)),
                    "funnel_km": a["funnel_km"]}
    return best


def cgwb_status(state):
    """CGWB regional groundwater category for a state ('overexploited'..'safe'), or None when
    the state is not in the index (scarcity then stays unscored rather than guessed)."""
    if not state:
        return None
    return _load().get("cgwb_state_status", {}).get(state)


if __name__ == "__main__":
    # Manali, Chennai sits inside the CEPI petrochemical cluster.
    m = nearest_cepi(13.166, 80.262)
    assert m and m["level"] == "critically_polluted", m
    # A remote point in the Bay of Bengal matches no cluster.
    assert nearest_cepi(10.0, 85.0) is None
    # Chennai airport funnel.
    assert nearest_airport(12.99, 80.17)["kind"] == "civil"
    assert cgwb_status("Tamil Nadu") == "overexploited"
    assert cgwb_status("Kerala") == "safe"
    assert cgwb_status("Atlantis") is None
    print("india_hazards offline OK")
