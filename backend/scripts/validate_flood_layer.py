"""Validate that the GCC flood CATEGORY field actually predicts observed flooding.

The 53 GCC-recorded 2020 (Cyclone Nivar) flood hotspots are an independent ground
truth: they are not derived from the inundation-zone polygons. If CATEGORY is
meaningful and correctly oriented, hotspots should concentrate in the high
categories far above those categories' share of the city's area.

Run:  python scripts/validate_flood_layer.py
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import cities  # noqa: E402
from app.core.geo import get_store, point_utm  # noqa: E402

ORDER = ["Very High", "High", "Moderate", "Low", "Very Low"]
RANK = {c: i for i, c in enumerate(reversed(ORDER), start=1)}
WINDOW_M = 100


def main():
    city = cities.get("chennai")
    store = get_store(city)
    fz = store.layer("flood_zones")
    hs = store.layer("flood_hotspots")
    if not len(fz) or not len(hs):
        print("missing layers; run scripts/ingest_kml.py first")
        return 1

    area = collections.Counter()
    for geom, props in zip(fz.geoms_utm, fz.props):
        area[props.get("CATEGORY", "?")] += geom.area
    total_area = sum(area[c] for c in ORDER)

    hits = collections.Counter()
    uncovered = 0
    for geom in hs.geoms_wgs:
        pt = point_utm(city, geom.y, geom.x)
        near = [fz.props[i].get("CATEGORY") for i in fz.within(pt, WINDOW_M)]
        near = [c for c in near if c in RANK]
        if not near:
            uncovered += 1
            continue
        hits[max(near, key=lambda c: RANK[c])] += 1
    total_hits = sum(hits.values())

    print("Flood layer validation - %d hotspots, %dm window" % (len(hs), WINDOW_M))
    print("(%d hotspots fall outside polygon coverage)\n" % uncovered)
    print("%-11s %10s %10s %8s" % ("CATEGORY", "area share", "hotspots", "lift"))
    for cat in ORDER:
        area_share = area[cat] / total_area if total_area else 0
        hit_share = hits[cat] / total_hits if total_hits else 0
        lift = (hit_share / area_share) if area_share else 0
        print("%-11s %9.1f%% %6d (%4.1f%%) %7.2fx" % (
            cat, 100 * area_share, hits[cat], 100 * hit_share, lift))

    top_share = (hits["Very High"] + hits["High"]) / total_hits if total_hits else 0
    top_area = (area["Very High"] + area["High"]) / total_area if total_area else 0
    print("\nHigh+Very High: %.1f%% of area captures %.1f%% of hotspots (%.1fx lift)"
          % (100 * top_area, 100 * top_share, top_share / top_area if top_area else 0))
    monotonic = all(
        (hits[a] / area[a] if area[a] else 0) >= (hits[b] / area[b] if area[b] else 0)
        for a, b in zip(ORDER, ORDER[1:]))
    print("Lift decreases monotonically down the scale: %s" % monotonic)
    return 0


if __name__ == "__main__":
    sys.exit(main())
