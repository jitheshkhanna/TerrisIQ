"""Layout export for Build Scope — setback envelope and indicative plotted layout.

Emits GeoJSON (plain JSON) and DXF (plain ASCII) with no GDAL/ezdxf dependency, so it fits
the Vercel serverless budget. Geometry is in LOCAL planar metres with the plot's front-left
corner at the origin (x east, y north). It is NOT georeferenced — georeferencing against the
survey centroid or a user pin-drop is a Phase-B step once a parcel source exists. The DXF is a
standard R12 entities file any CAD tool opens.

An "indicative plotted layout" is a screening sketch, not a sanctioned Rule-47 layout: it
shows one reasonable subdivision given the plot rectangle, an internal road and an OSR plot.
The engine in build_scope.py owns the regulatory numbers; this module only draws rectangles.
"""
import math
from typing import List, Optional, Tuple

Ring = List[Tuple[float, float]]


def _dims_from_area(area_sqm: float, width_m: Optional[float], depth_m: Optional[float]):
    """Resolve a plot rectangle. Width/depth win; otherwise assume a square from the area."""
    if width_m and depth_m:
        return float(width_m), float(depth_m)
    if width_m:
        return float(width_m), area_sqm / float(width_m)
    if depth_m:
        return area_sqm / float(depth_m), float(depth_m)
    side = math.sqrt(area_sqm)
    return side, side


def _rect(x0, y0, x1, y1) -> Ring:
    """Closed rectangle ring, counter-clockwise."""
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def _feature(ring: Ring, props: dict) -> dict:
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [[[round(x, 3), round(y, 3)]
                                                          for x, y in ring]]},
    }


def setback_envelope(area_sqm, setbacks, width_m=None, depth_m=None) -> dict:
    """GeoJSON FeatureCollection: the plot boundary and the buildable envelope inside the
    setbacks. `setbacks` is the dict from build_scope() (front_m/side1_m/side2_m/rear_m)."""
    w, d = _dims_from_area(area_sqm, width_m, depth_m)
    front = setbacks.get("front_m", 3.0)
    rear = setbacks.get("rear_m", 3.0)
    s1 = setbacks.get("side1_m", 1.5)
    s2 = setbacks.get("side2_m", 1.5)

    plot = _rect(0, 0, w, d)
    # Front is the y=0 edge (road side); rear the far edge.
    bx0, by0, bx1, by1 = s1, front, w - s2, d - rear
    features = [_feature(plot, {"name": "Plot boundary", "area_sqm": round(w * d, 1),
                                "width_m": round(w, 2), "depth_m": round(d, 2)})]
    buildable_ok = bx1 > bx0 and by1 > by0
    if buildable_ok:
        features.append(_feature(_rect(bx0, by0, bx1, by1), {
            "name": "Buildable envelope (after setbacks)",
            "area_sqm": round((bx1 - bx0) * (by1 - by0), 1)}))
    return {
        "type": "FeatureCollection",
        "crs_note": "Local planar metres, front-left corner at origin; not georeferenced.",
        "buildable": buildable_ok,
        "features": features,
    }


def plotted_layout(area_sqm, width_m=None, depth_m=None, target_plot_sqm=150.0,
                   road_width_m=9.0, osr_fraction=0.10) -> dict:
    """One indicative subdivision: a central spine road, individual plots along both sides,
    and an OSR plot. Returns a GeoJSON FeatureCollection plus a plot schedule."""
    w, d = _dims_from_area(area_sqm, width_m, depth_m)
    features = [_feature(_rect(0, 0, w, d), {"name": "Layout boundary",
                                             "area_sqm": round(w * d, 1)})]
    schedule = []

    # Central road running front-to-rear, splitting the plot into two rows.
    road_x0 = max(0.0, w / 2 - road_width_m / 2)
    road_x1 = min(w, road_x0 + road_width_m)
    features.append(_feature(_rect(road_x0, 0, road_x1, d),
                             {"name": "Internal road", "width_m": road_width_m}))

    # OSR plot reserved at the rear.
    osr_depth = max(0.0, (area_sqm * osr_fraction) / w)
    osr_y0 = max(0.0, d - osr_depth)
    if osr_depth > 0:
        features.append(_feature(_rect(0, osr_y0, w, d),
                                 {"name": "OSR / open space", "area_sqm": round(w * osr_depth, 1)}))

    usable_depth = osr_y0
    plot_frontage = max(4.5, math.sqrt(target_plot_sqm))  # frontage per plot
    n = 0
    for (rx0, rx1, side) in ((0.0, road_x0, "W"), (road_x1, w, "E")):
        row_w = rx1 - rx0
        if row_w <= 0:
            continue
        plot_depth = usable_depth
        count = max(1, int(row_w // plot_frontage))
        fw = row_w / count
        for i in range(count):
            px0 = rx0 + i * fw
            ring = _rect(px0, 0, px0 + fw, plot_depth)
            n += 1
            a = round(fw * plot_depth, 1)
            schedule.append({"plot_no": n, "side": side, "frontage_m": round(fw, 2),
                             "depth_m": round(plot_depth, 2), "area_sqm": a})
            features.append(_feature(ring, {"name": "Plot %d" % n, "area_sqm": a}))

    return {
        "type": "FeatureCollection",
        "crs_note": "Local planar metres, front-left corner at origin; not georeferenced.",
        "plot_count": n,
        "schedule": schedule,
        "features": features,
        "disclaimer": "Indicative subdivision sketch only — not a sanctioned Rule-47 layout.",
    }


def to_dxf(geojson: dict) -> str:
    """Minimal AutoCAD R12 ASCII DXF from a GeoJSON FeatureCollection of polygons. One
    POLYLINE per ring, layer-named from the feature's `name`. Opens in any CAD tool."""
    out = ["0", "SECTION", "2", "ENTITIES"]
    for feat in geojson.get("features", []):
        name = str(feat.get("properties", {}).get("name", "LAYOUT")).upper().replace(" ", "_")[:31]
        for ring in feat.get("geometry", {}).get("coordinates", []):
            out += ["0", "POLYLINE", "8", name, "66", "1", "70", "1"]
            for x, y in ring:
                out += ["0", "VERTEX", "8", name, "10", "%.3f" % x, "20", "%.3f" % y, "30", "0.0"]
            out += ["0", "SEQEND", "8", name]
    out += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(out) + "\n"
