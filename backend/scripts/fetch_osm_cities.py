"""Pull the OpenStreetMap baseline for every city.

OSM is the one source that exists everywhere, so it is what makes a city scoreable at
all when its corporation publishes nothing.

One request per city, not one per layer. Overpass rate-limits by IP and starts refusing
connections outright after a few cities, so everything a city needs comes back in a
single query and is split by tag locally.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.cities import CITIES  # noqa: E402
from scripts.fetch_osm import PROCESSED_DIR, element_to_feature, run_query  # noqa: E402

COASTAL = {"mumbai", "chennai", "kolkata"}
OSM_WARDS = {"delhi", "ahmedabad"}  # neither publishes an open ward file

COMBINED = """
[out:json][timeout:300];
(
  way["natural"="water"](%(bbox)s);
  relation["natural"="water"](%(bbox)s);
  way["landuse"="reservoir"](%(bbox)s);
  way["waterway"~"^(river|canal|drain|stream)$"](%(bbox)s);
  relation["waterway"~"^(river|canal)$"](%(bbox)s);
  way["natural"="wetland"](%(bbox)s);
  way["landuse"="industrial"](%(bbox)s);
  relation["landuse"="industrial"](%(bbox)s);
  way["man_made"="works"](%(bbox)s);
  way["landuse"="landfill"](%(bbox)s);
  relation["landuse"="landfill"](%(bbox)s);
  node["amenity"="waste_disposal"](%(bbox)s);
  way["amenity"="waste_disposal"](%(bbox)s);
%(coast)s);
out geom;
"""

WARDS = """
[out:json][timeout:300];
(
  relation["boundary"="administrative"]["admin_level"~"^(9|10)$"](%(bbox)s);
);
out geom;
"""


def classify(props):
    """Which layer this feature belongs to, from its tags."""
    if props.get("landuse") == "landfill" or props.get("amenity") == "waste_disposal":
        return "landfill"
    if props.get("natural") == "coastline":
        return "coastline"
    if props.get("landuse") == "industrial" or props.get("man_made") == "works":
        return "industrial"
    if (props.get("natural") in ("water", "wetland") or props.get("waterway")
            or props.get("landuse") == "reservoir"):
        return "waterbodies"
    return None


def write(city, kind, feats):
    # Never write an empty layer. Overpass sometimes answers a timed-out query with a
    # valid, empty body; persisting that makes the registry believe the layer exists and
    # silently scores the city against nothing.
    if not feats:
        print("     %-12s EMPTY response, not written (will retry next run)" % kind)
        return
    path = os.path.join(PROCESSED_DIR, "%s_%s.geojson" % (city.slug, kind))
    with open(path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh, separators=(",", ":"))
    print("     %-12s %5d features  %.2f MB" % (kind, len(feats), os.path.getsize(path) / 1e6))


def needed(city):
    kinds = ["waterbodies", "industrial", "landfill"]
    if city.slug in COASTAL:
        kinds.append("coastline")
    return [k for k in kinds
            if not os.path.exists(os.path.join(PROCESSED_DIR, "%s_%s.geojson" % (city.slug, k)))]


def main():
    only = sys.argv[1:] or None
    for city in CITIES.values():
        if city.slug == "chennai" or (only and city.slug not in only):
            continue
        missing = needed(city)
        want_wards = (city.slug in OSM_WARDS and not os.path.exists(
            os.path.join(PROCESSED_DIR, "%s_wards.geojson" % city.slug)))
        if not missing and not want_wards:
            print("== %s: complete" % city.name)
            continue

        lat_min, lng_min, lat_max, lng_max = city.bbox
        bbox = "%s,%s,%s,%s" % (lat_min, lng_min, lat_max, lng_max)
        print("== %s (need: %s)" % (city.name, ", ".join(missing) or "wards only"))

        if missing:
            coast = ('  way["natural"="coastline"](%s);\n' % bbox) if city.slug in COASTAL else ""
            try:
                data = run_query(COMBINED % {"bbox": bbox, "coast": coast})
            except Exception as exc:  # noqa: BLE001 - a failed city degrades, it does not stop the run
                print("   ! %s" % exc)
                data = None
            if data:
                buckets = {"waterbodies": [], "industrial": [], "landfill": [], "coastline": []}
                for el in data.get("elements", []):
                    feat = element_to_feature(el)
                    if feat is None:
                        continue
                    kind = classify(feat["properties"])
                    if kind in buckets:
                        buckets[kind].append(feat)
                for kind in missing:
                    write(city, kind, buckets.get(kind, []))
                time.sleep(6)

        if want_wards:
            try:
                data = run_query(WARDS % {"bbox": bbox})
                feats = [f for f in (element_to_feature(e) for e in data.get("elements", []))
                         if f is not None]
                write(city, "wards", feats)
                time.sleep(6)
            except Exception as exc:  # noqa: BLE001
                print("   ! wards: %s" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
