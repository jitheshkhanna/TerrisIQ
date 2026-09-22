"""Download GCC/OpenCity KML sources and convert them to compact GeoJSON.

The upstream KMLs are large (flood zones ~40 MB, storm water drains ~28 MB) so we
stream them with iterparse and keep only the attributes the scoring engines use.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW_DIR = os.path.join(ROOT, "data", "raw")
PROCESSED_DIR = os.path.join(ROOT, "data", "processed")

KML_NS = "{http://www.opengis.net/kml/2.2}"

SOURCES = {
    "flood_hazard_zones": {
        "url": "https://data.opencity.in/dataset/chennai-flooding-data/resource/"
               "e61afe07-0f52-4be9-bdf3-5eb0f62b2ed6/download/"
               "7f29da20-6621-4b49-b0cf-28b9d1de232b.kml",
        "keep": ["CATEGORY"],
    },
    "flood_hotspots_2020": {
        "url": "https://data.opencity.in/dataset/3aef2eef-a97e-4fac-a4a9-aaa42a91fbfa/resource/"
               "068cfdae-652d-47c9-9722-7c49396d8a05/download/"
               "3a141c21-2b9d-4fc0-bd96-d71650a8a15a.kml",
        "keep": ["slno"],
    },
    # Ward and zone boundaries let the tool answer in the vocabulary property paperwork
    # uses, from a query typed in everyday language.
    "gcc_wards_2022": {
        "url": "https://data.opencity.in/dataset/c77de7f8-e377-4990-90fc-4f0f8ca0e2d2/resource/"
               "e90176d4-319a-45bd-918e-ecce4f048c4d/download/"
               "6a8a05ed-a41c-492a-aade-ff7517e1a4b1.kml",
        "keep": ["name"],
    },
    "gcc_zones_2022": {
        "url": "https://data.opencity.in/dataset/c77de7f8-e377-4990-90fc-4f0f8ca0e2d2/resource/"
               "00b3ea2e-e3a4-4b28-aec2-769a01404e5b/download/"
               "0f0ccbda-9485-4964-b3b1-6ce53af82bbb.kml",
        "keep": ["ZONE", "ZONE_NAME", "Region"],
    },
    "swd_network": {
        "url": "https://data.opencity.in/dataset/e71414ae-d144-4e69-866d-48762c337929/resource/"
               "107ac467-2381-4718-9632-645560bc8360/download/"
               "c4907fed-934b-4342-a3f4-74226853719d.kml",
        "keep": ["DRAIN_TYPE", "DRAIN_WID", "DRAIN_DEP", "STATUS", "COVER",
                 "WATER_FLOW", "WARD", "ZONE", "LOCATION", "ST_NAME"],
    },
}


def download(name, url):
    path = os.path.join(RAW_DIR, name + ".kml")
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        print("  cached: %s (%.1f MB)" % (path, os.path.getsize(path) / 1e6))
        return path
    print("  downloading %s ..." % name)
    resp = requests.get(url, timeout=600, stream=True)
    resp.raise_for_status()
    with open(path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
    print("  saved %s (%.1f MB)" % (path, os.path.getsize(path) / 1e6))
    return path


def parse_coords(text):
    """KML coordinate string -> list of [lon, lat] (altitude dropped)."""
    pts = []
    for tok in text.split():
        parts = tok.split(",")
        if len(parts) >= 2:
            pts.append([round(float(parts[0]), 7), round(float(parts[1]), 7)])
    return pts


def placemark_geometry(pm):
    """Extract the first supported geometry from a Placemark as GeoJSON."""
    point = pm.find(".//%sPoint/%scoordinates" % (KML_NS, KML_NS))
    if point is not None and point.text:
        pts = parse_coords(point.text)
        if pts:
            return {"type": "Point", "coordinates": pts[0]}

    polys = pm.findall(".//%sPolygon" % KML_NS)
    if polys:
        rings_per_poly = []
        for poly in polys:
            rings = []
            outer = poly.find("%souterBoundaryIs/%sLinearRing/%scoordinates" % (KML_NS, KML_NS, KML_NS))
            if outer is None or not outer.text:
                continue
            ring = parse_coords(outer.text)
            if len(ring) < 4:
                continue
            rings.append(ring)
            for inner in poly.findall("%sinnerBoundaryIs/%sLinearRing/%scoordinates" % (KML_NS, KML_NS, KML_NS)):
                if inner.text:
                    hole = parse_coords(inner.text)
                    if len(hole) >= 4:
                        rings.append(hole)
            rings_per_poly.append(rings)
        if not rings_per_poly:
            return None
        if len(rings_per_poly) == 1:
            return {"type": "Polygon", "coordinates": rings_per_poly[0]}
        return {"type": "MultiPolygon", "coordinates": rings_per_poly}

    lines = pm.findall(".//%sLineString/%scoordinates" % (KML_NS, KML_NS))
    if lines:
        parts = [parse_coords(ls.text) for ls in lines if ls.text]
        parts = [p for p in parts if len(p) >= 2]
        if not parts:
            return None
        if len(parts) == 1:
            return {"type": "LineString", "coordinates": parts[0]}
        return {"type": "MultiLineString", "coordinates": parts}
    return None


def placemark_props(pm, keep):
    props = {}
    name = pm.find("%sname" % KML_NS)
    if name is not None and name.text and name.text.strip():
        props["name"] = name.text.strip()
    for sd in pm.findall(".//%sSimpleData" % KML_NS):
        key = sd.get("name")
        if key in keep:
            val = (sd.text or "").strip()
            if val:
                props[key] = val
    return props


def convert(name, kml_path, keep):
    out_path = os.path.join(PROCESSED_DIR, name + ".geojson")
    features = []
    skipped = 0
    context = ET.iterparse(kml_path, events=("end",))
    for _, elem in context:
        if elem.tag != "%sPlacemark" % KML_NS:
            continue
        geom = placemark_geometry(elem)
        if geom is None:
            skipped += 1
        else:
            features.append({
                "type": "Feature",
                "properties": placemark_props(elem, keep),
                "geometry": geom,
            })
        elem.clear()
    with open(out_path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
    print("  -> %s (%d features, %d skipped, %.1f MB)"
          % (out_path, len(features), skipped, os.path.getsize(out_path) / 1e6))
    return out_path


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    for name, spec in SOURCES.items():
        print("[%s]" % name)
        kml_path = download(name, spec["url"])
        convert(name, kml_path, set(spec["keep"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
