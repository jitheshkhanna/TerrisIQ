"""CRZ (Coastal Regulation Zone) screening from the open OpenStreetMap coastline (ODbL).

This is a distance-to-coast PROXY, not the official Coastal Zone Management Plan (CZMP),
which is authoritative and overrides it. Under the CRZ notification the regulated zone runs
to 500 m from the High Tide Line, with a 50-200 m no-development zone by density class. We
flag the band and tell the user to verify against the approved CZMP. Returns None when the
point is inland (no coastline layer, or more than 500 m away).
"""
from app.core.geo import get_store, point_utm

_CRZ_OUTER_M = 500.0
_NDZ_M = 200.0


def crz_screen(city, lat, lng):
    store = get_store(city)
    layer = store.layer("coastline")
    if not len(layer):
        return None
    idx, dist, _ = layer.nearest_with_props(point_utm(city, lat, lng))
    if idx is None or dist is None or dist > _CRZ_OUTER_M:
        return None
    if dist <= _NDZ_M:
        band = "no-development"
        headline = ("Coast ~%dm away — likely a CRZ no-development zone." % round(dist))
    else:
        band = "regulated"
        headline = ("Coast ~%dm away — inside the Coastal Regulation Zone; "
                    "building is restricted." % round(dist))
    return {
        "applicable": True,
        "band": band,
        "distance_m": round(dist),
        "headline": headline,
        "note": "Screening estimate from the coastline, not the official zone. Verify against "
                "the approved Coastal Zone Management Plan (CZMP) before relying on it.",
    }
