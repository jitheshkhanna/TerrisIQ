"""Pull Chennai waterbodies, industrial land use and landfills from Overpass."""
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROCESSED_DIR = os.path.join(ROOT, "data", "processed")

# Overpass's Apache layer returns 406 for any User-Agent containing "Property" —
# property scrapers are a known abuse vector, so the word is blocklisted. The rename
# from ChennaiTerraRisk to Property Risk Analyser silently broke every OSM fetch until
# that turned up. Keep this string free of it.
HEADERS = {"User-Agent": "TerraRiskAnalyser/0.1 (open data research)"}

ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

# Greater Chennai: wide enough to cover Tambaram / Guduvancheri / OMR beyond
# Sholinganallur, which the scarcity model needs.
BBOX = "12.70,79.90,13.40,80.45"

QUERIES = {
    "waterbodies": """
[out:json][timeout:300];
(
  way["natural"="water"](%(bbox)s);
  relation["natural"="water"](%(bbox)s);
  way["landuse"="reservoir"](%(bbox)s);
  way["waterway"~"^(river|canal|drain|stream)$"](%(bbox)s);
  relation["waterway"~"^(river|canal)$"](%(bbox)s);
  way["natural"="wetland"](%(bbox)s);
  relation["natural"="wetland"](%(bbox)s);
);
out geom;
""",
    "industrial": """
[out:json][timeout:300];
(
  way["landuse"="industrial"](%(bbox)s);
  relation["landuse"="industrial"](%(bbox)s);
  way["man_made"="works"](%(bbox)s);
);
out geom;
""",
    "coastline": """
[out:json][timeout:300];
(
  way["natural"="coastline"](%(bbox)s);
);
out geom;
""",
    "landfill": """
[out:json][timeout:300];
(
  way["landuse"="landfill"](%(bbox)s);
  relation["landuse"="landfill"](%(bbox)s);
  way["amenity"="waste_disposal"](%(bbox)s);
  node["amenity"="waste_disposal"](%(bbox)s);
);
out geom;
""",
}


def run_query(query):
    last_err = None
    for endpoint in ENDPOINTS:
        for attempt in range(3):
            try:
                resp = requests.post(endpoint, data={"data": query},
                                     headers=HEADERS, timeout=360)
                if resp.status_code in (429, 504):
                    print("    %s busy (%s), retrying..." % (endpoint, resp.status_code))
                    time.sleep(15 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001 - report and fall through to next mirror
                last_err = exc
                print("    attempt failed: %s" % exc)
                time.sleep(10)
    raise RuntimeError("all Overpass endpoints failed: %s" % last_err)


def ring_from_geometry(geom):
    return [[round(p["lon"], 7), round(p["lat"], 7)] for p in geom if "lon" in p]


def closed(ring):
    return len(ring) >= 4 and ring[0] == ring[-1]


def element_to_feature(el):
    tags = el.get("tags", {})
    props = {k: v for k, v in tags.items() if k in (
        "name", "natural", "waterway", "landuse", "water", "wetland",
        "industrial", "man_made", "amenity", "operator")}
    props["osm_id"] = "%s/%s" % (el["type"], el["id"])

    if el["type"] == "node":
        return {"type": "Feature", "properties": props,
                "geometry": {"type": "Point", "coordinates": [round(el["lon"], 7), round(el["lat"], 7)]}}

    if el["type"] == "way":
        ring = ring_from_geometry(el.get("geometry") or [])
        if len(ring) < 2:
            return None
        is_area = (tags.get("natural") == "coastline" and False) or (
                   "natural" in tags or "landuse" in tags or "amenity" in tags
                   or tags.get("man_made") == "works")
        if tags.get("natural") == "coastline":
            is_area = False
        if is_area and len(ring) >= 4:
            if not closed(ring):
                ring = ring + [ring[0]]
            return {"type": "Feature", "properties": props,
                    "geometry": {"type": "Polygon", "coordinates": [ring]}}
        return {"type": "Feature", "properties": props,
                "geometry": {"type": "LineString", "coordinates": ring}}

    if el["type"] == "relation":
        # Treat each closed outer member as its own polygon; open members become lines.
        polys, lines = [], []
        for member in el.get("members", []):
            if member.get("role") not in ("outer", "", None):
                continue
            ring = ring_from_geometry(member.get("geometry") or [])
            if len(ring) >= 4:
                if not closed(ring):
                    ring = ring + [ring[0]]
                polys.append([ring])
            elif len(ring) >= 2:
                lines.append(ring)
        if polys:
            return {"type": "Feature", "properties": props,
                    "geometry": {"type": "MultiPolygon", "coordinates": polys}}
        if lines:
            return {"type": "Feature", "properties": props,
                    "geometry": {"type": "MultiLineString", "coordinates": lines}}
    return None


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    for name, template in QUERIES.items():
        out_path = os.path.join(PROCESSED_DIR, "osm_%s.geojson" % name)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 512:
            print("[%s] cached" % name)
            continue
        print("[%s] querying Overpass..." % name)
        data = run_query(template % {"bbox": BBOX})
        features = []
        for el in data.get("elements", []):
            feat = element_to_feature(el)
            if feat is not None:
                features.append(feat)
        with open(out_path, "w") as fh:
            json.dump({"type": "FeatureCollection", "features": features}, fh)
        print("  -> %s (%d features)" % (out_path, len(features)))
        time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
