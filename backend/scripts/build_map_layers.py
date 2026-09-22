"""Precompute lightweight GeoJSON for the map, per city.

Raw layers are far too heavy to hand a browser: Chennai's flood polygons are 33 MB and
Bengaluru's drain network 20 MB. Everything is simplified in metric space so the
tolerance is a real distance, slivers are dropped, and only the properties the map
legend uses survive.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import shapely  # noqa: E402
from pyproj import Transformer  # noqa: E402
from shapely.geometry import mapping  # noqa: E402

from app.core.cities import CITIES  # noqa: E402
from app.core.geo import PROCESSED_DIR, get_store  # noqa: E402

OUT_DIR = os.path.join(PROCESSED_DIR, "map")

SPECS = {
    "flood_zones": {"tolerance_m": 8.0, "min_area_m2": 750.0, "keep": ["CATEGORY"]},
    "low_lying": {"tolerance_m": 8.0, "min_area_m2": 400.0, "keep": ["name"]},
    "swd": {"tolerance_m": 6.0, "min_area_m2": 0.0, "keep": ["DRAIN_TYPE", "STATUS", "WARD"]},
    "waterbodies": {"tolerance_m": 8.0, "min_area_m2": 400.0,
                    "keep": ["name", "natural", "waterway"]},
    "industrial": {"tolerance_m": 10.0, "min_area_m2": 750.0, "keep": ["name", "landuse"]},
    "flood_hotspots": {"tolerance_m": 0.0, "min_area_m2": 0.0, "keep": ["name"]},
    "wards": {"tolerance_m": 12.0, "min_area_m2": 0.0,
              "keep": ["name", "name_en", "id", "ward", "WARD", "qwr", "CIRCLE"]},
    "zones": {"tolerance_m": 20.0, "min_area_m2": 0.0, "keep": ["ZONE_NAME", "name"]},
}


def build(city, name, spec, to_wgs):
    store = get_store(city)
    layer = store.layer(name)
    if not len(layer):
        return
    features, dropped = [], 0
    for geom_utm, props in zip(layer.geoms_utm, layer.props):
        if spec["min_area_m2"] and geom_utm.area and geom_utm.area < spec["min_area_m2"]:
            dropped += 1
            continue
        g = geom_utm
        if spec["tolerance_m"]:
            g = g.simplify(spec["tolerance_m"], preserve_topology=True)
            if g.is_empty:
                dropped += 1
                continue
        back = shapely.transform(g, lambda c: np.column_stack(to_wgs.transform(c[:, 0], c[:, 1])))
        features.append({
            "type": "Feature",
            "properties": {k: props.get(k) for k in spec["keep"] if props.get(k) is not None},
            "geometry": json.loads(json.dumps(mapping(back))),
        })
    path = os.path.join(OUT_DIR, "%s_%s.geojson" % (city.slug, name))
    with open(path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, separators=(",", ":"))
    print("   %-16s %5d features (%d dropped) %6.2f MB"
          % (name, len(features), dropped, os.path.getsize(path) / 1e6))


def dumpsites(city):
    """Chennai's curated dumpsite points; no other city has an equivalent file."""
    if city.slug != "chennai":
        return
    from app.core.geo import MANUAL_DIR
    src = os.path.join(MANUAL_DIR, "dumpsites.json")
    if not os.path.exists(src):
        return
    with open(src) as fh:
        records = json.load(fh)
    feats = [{"type": "Feature",
              "properties": {k: v for k, v in r.items() if k not in ("lat", "lng")},
              "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]}}
             for r in records]
    path = os.path.join(OUT_DIR, "%s_dumpsites.geojson" % city.slug)
    with open(path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh)
    print("   %-16s %5d features" % ("dumpsites", len(feats)))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    only = sys.argv[1:] or None
    total = 0
    for city in CITIES.values():
        if only and city.slug not in only:
            continue
        print("== %s" % city.name)
        to_wgs = Transformer.from_crs("EPSG:%d" % city.epsg, "EPSG:4326", always_xy=True)
        for name, spec in SPECS.items():
            build(city, name, spec, to_wgs)
        dumpsites(city)
    for f in os.listdir(OUT_DIR):
        total += os.path.getsize(os.path.join(OUT_DIR, f))
    print("\nmap layer total: %.1f MB" % (total / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
