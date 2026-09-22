"""End-to-end scoring checks against the brief's success criteria.

Covers:
  * latency (target: a composite score in under 3 seconds)
  * PDF generation time (target: under 5 seconds)
  * behaviour on known flood-prone vs. known low-risk localities
  * graceful degradation outside each dataset's surveyed extent

Run:  python scripts/validate_scoring.py
"""
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.core.elevation as elevation  # noqa: E402
from app.core.geo import STORE, utm_to_wgs  # noqa: E402
from app.core.scoring import assess  # noqa: E402
from app.engines.flood import calculate_flood_risk  # noqa: E402
from app.pdf.generator import build_report  # noqa: E402

# Localities the project brief names as flood-prone, and control points that should
# not light up the flood model.
FLOOD_PRONE = [
    ("Velachery", 12.9783, 80.2209),
    ("Pallikaranai", 12.9400, 80.2100),
    ("Madipakkam", 12.9630, 80.1990),
    ("Perumbakkam", 12.9060, 80.2050),
    ("Vyasarpadi", 13.1150, 80.2550),
    ("Kodungaiyur", 13.1326, 80.2524),
    ("Mudichur", 12.9080, 80.0700),
    ("Thoraipakkam", 12.9250, 80.2280),
]
CONTROLS = [
    ("Anna Nagar West", 13.0850, 80.2010),
    ("Nungambakkam", 13.0569, 80.2425),
    ("Adyar", 13.0067, 80.2570),
    ("Besant Nagar", 13.0002, 80.2668),
]
CONTAMINATION_EXPECTED_HIGH = [
    ("Manali", 13.1647, 80.2587),
    ("Ambattur Industrial Estate", 13.1143, 80.1548),
    ("Perungudi (dumpyard)", 12.9576, 80.2422),
]


def flood_discrimination():
    """The real test of the flood model: does its score separate places that actually
    flooded from ordinary parcels?

    The 53 GCC-recorded 2020 (Cyclone Nivar) hotspots are independent of the inundation
    polygons the score is built from, so they make honest ground truth. We compare them
    against parcels drawn at random from inside the same surveyed footprint, weighted by
    polygon area so the sample mirrors "a random parcel in the surveyed city".

    Elevation is stubbed out here: it costs a network call per point, and this test is
    measuring the spatial signals.
    """
    original = elevation.elevation_profile
    elevation.elevation_profile = lambda lat, lng: {
        "elevation_m": None, "neighbourhood_mean_m": None, "relative_m": None,
        "source": None, "available": False}
    try:
        hotspots = STORE.layer("flood_hotspots")
        zones = STORE.layer("flood_zones")
        hot = [calculate_flood_risk(g.y, g.x)["score"] for g in hotspots.geoms_wgs]

        random.seed(7)
        weights = [g.area for g in zones.geoms_utm]
        picks = random.choices(range(len(zones.geoms_utm)), weights=weights, k=300)
        control = []
        for i in picks:
            point = zones.geoms_utm[i].representative_point()
            lat, lng = utm_to_wgs(point.x, point.y)
            control.append(calculate_flood_risk(lat, lng)["score"])
    finally:
        elevation.elevation_profile = original

    def describe(name, values):
        ordered = sorted(values)
        print("%-24s n=%3d mean=%5.1f median=%5.1f p25=%4.1f p75=%4.1f"
              % (name, len(ordered), statistics.mean(ordered), statistics.median(ordered),
                 ordered[len(ordered) // 4], ordered[3 * len(ordered) // 4]))

    print("\nFlood score vs. independent ground truth")
    describe("2020 recorded hotspots", hot)
    describe("random GCC parcels", control)
    print("separation: %+.1f points" % (statistics.mean(hot) - statistics.mean(control)))
    for threshold in (40, 50, 60):
        hit = sum(1 for v in hot if v >= threshold) / len(hot)
        base = sum(1 for v in control if v >= threshold) / len(control)
        print("  scoring >=%d: hotspots %4.0f%%  random %4.0f%%  lift %.1fx"
              % (threshold, 100 * hit, 100 * base, (hit / base) if base else 0))


def run_group(title, places):
    print("\n%s" % title)
    print("%-28s %7s %7s %7s %8s  %-6s %s"
          % ("locality", "flood", "contam", "scarce", "compos", "grade", "confidence"))
    rows = []
    for name, lat, lng in places:
        result = assess(lat, lng, name, use_cache=False)
        rows.append(result)
        print("%-28s %7d %7d %7d %8d  %-6s %s"
              % (name[:28], result["flood"]["score"], result["contamination"]["score"],
                 result["scarcity"]["score"], result["composite_score"],
                 result["composite_grade"], result["confidence"]))
    return rows


def main():
    STORE.load()

    flood_discrimination()

    print("\nPer-locality spot checks. These are single points at locality centroids, so"
          "\nthey illustrate output rather than validate it - a centroid says nothing about"
          "\nthe parcel next door, which is the whole reason this tool scores points, not"
          "\nneighbourhoods. Use the discrimination test above to judge the model.")
    flood_rows = run_group("Brief-listed flood-prone localities", FLOOD_PRONE)
    control_rows = run_group("Control localities", CONTROLS)
    contam_rows = run_group("Known industrial / waste zones", CONTAMINATION_EXPECTED_HIGH)

    print("\n--- separation (contamination) ---")
    contam_mean = statistics.mean(r["contamination"]["score"] for r in contam_rows)
    control_contam = statistics.mean(r["contamination"]["score"] for r in control_rows)
    print("mean contamination, industrial zones:       %.1f" % contam_mean)
    print("mean contamination, controls:               %.1f" % control_contam)
    print("separation: %+.1f points" % (contam_mean - control_contam))

    print("\n--- latency (success criterion: score < 3s, PDF < 5s) ---")
    timings = []
    for name, lat, lng in FLOOD_PRONE:
        start = time.time()
        assess(lat, lng, name, use_cache=False)
        timings.append(time.time() - start)
    print("uncached score: mean %.3fs, max %.3fs (n=%d)"
          % (statistics.mean(timings), max(timings), len(timings)))

    start = time.time()
    for name, lat, lng in FLOOD_PRONE:
        assess(lat, lng, name)
    print("cached score:   mean %.4fs" % ((time.time() - start) / len(FLOOD_PRONE)))

    result = assess(12.9783, 80.2209, "Velachery")
    start = time.time()
    pdf = build_report(result)
    print("PDF report:     %.3fs (%d KB, 3 pages)" % (time.time() - start, len(pdf) // 1024))

    print("\n--- degradation outside surveyed extent ---")
    for name, lat, lng in [("Guduvancheri (outside GCC)", 12.8450, 80.0600),
                           ("Kelambakkam (outside GCC)", 12.7900, 80.2200)]:
        result = assess(lat, lng, name, use_cache=False)
        print("%-28s composite %2d grade %s confidence=%s"
              % (name, result["composite_score"], result["composite_grade"],
                 result["confidence"]))
        for warning in result["flood"]["warnings"][:1]:
            print("    %s" % warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
