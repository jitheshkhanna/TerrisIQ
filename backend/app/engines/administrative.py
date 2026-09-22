"""Translate a point into the vocabulary local property paperwork actually uses.

Buyers search in everyday language. Patta records, corporation applications and water
connections are filed against a ward. This closes that gap.

Every corporation names and numbers its wards differently, and their published files
reflect that: Chennai numbers wards 1-200 inside 15 named zones, Mumbai uses letter
codes like G/S, Bengaluru names its 225 BBMP wards, Hyderabad packs ward, circle and
zone into one record, Pune publishes prabhag numbers with no names at all, and Delhi and
Ahmedabad publish nothing, so their wards come from OpenStreetMap. Each city therefore
gets its own reader rather than a lowest-common-denominator guess.
"""
from app.core.geo import get_store, point_utm

# How far outside a boundary we will still name it, for a pin dropped on a road edge.
EDGE_TOLERANCE_M = 60

# Cities with no published corporation ward file. What we have instead is OpenStreetMap
# admin levels 9-10, which are villages, colonies and sectors: they do not tile the
# city, so a containment test says "outside the corporation" in the middle of Connaught
# Place. For these we name the nearest locality as context and make no boundary claim.
UNOFFICIAL_BOUNDARIES = {"delhi", "ahmedabad"}
LOCALITY_RADIUS_M = 2500

CHENNAI_ZONE_DISPLAY = {
    "THIRUVOTTRIYUR": "Thiruvottiyur", "MANALI": "Manali", "MADHAVARAM": "Madhavaram",
    "TONDIARPET": "Tondiarpet", "ROYAPURAM": "Royapuram",
    "THIRU-VIKA-NAGAR": "Thiru Vi Ka Nagar", "AMBATTUR": "Ambattur",
    "ANNA NAGAR": "Anna Nagar", "TEYNAMPET": "Teynampet", "KODAMBAKKAM": "Kodambakkam",
    "VALASARVAKKAM": "Valasaravakkam", "ALANDUR": "Alandur", "ADYAR": "Adyar",
    "PERUNKUDI": "Perungudi", "SHOZHANGANALLUR": "Sholinganallur",
}
CHENNAI_ZONE_NUMBER = {
    "Thiruvottiyur": 1, "Manali": 2, "Madhavaram": 3, "Tondiarpet": 4, "Royapuram": 5,
    "Thiru Vi Ka Nagar": 6, "Ambattur": 7, "Anna Nagar": 8, "Teynampet": 9,
    "Kodambakkam": 10, "Valasaravakkam": 11, "Alandur": 12, "Adyar": 13,
    "Perungudi": 14, "Sholinganallur": 15,
}


def _titlecase(value):
    """SHOUTY municipal names to something readable, leaving mixed case alone.

    Handles "GUNFOUNDRY(ABIDS)" as well as plain words, since these files punctuate
    without spaces.
    """
    if not value:
        return None
    import re
    text = str(value).strip()
    if not any(c.islower() for c in text):
        text = re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), text.lower())
    return " ".join(text.split())


def _split_numbered(value):
    """'127-RANGAREDDY NAGAR' -> ('127', 'Rangareddy Nagar')."""
    text = str(value or "").strip()
    if "-" in text:
        head, _, tail = text.partition("-")
        if head.strip().isdigit():
            return head.strip(), _titlecase(tail)
    return None, _titlecase(text) or None


# --- per-city readers: props -> (ward_number, ward_name, zone_name) -------------------

def _read_chennai(props):
    return (props.get("name") or "").strip() or None, None, None


def _read_mumbai(props):
    # BMC wards are letter codes (A, G/S, K/W), not numbers.
    return None, (props.get("name") or "").strip() or None, None


def _read_bengaluru(props):
    number = (props.get("id") or "").strip() or None
    name = _titlecase(props.get("name_en") or props.get("proposed_ward_name_en"))
    if name and "-" in str(name) and not props.get("name_en"):
        _, name = _split_numbered(name)
    return number, name, None


def _read_hyderabad(props):
    number, name = _split_numbered(props.get("ward"))
    zone = _titlecase(props.get("ZONE"))
    if zone and zone.lower().endswith(" zone"):
        zone = zone[: -len(" zone")]
    circle = _split_numbered(props.get("CIRCLE"))[1]
    if circle and not zone:
        zone = circle
    return number, name, zone


def _read_pune(props):
    # PMC's electoral ward file carries only "qwr", the prabhag number as a float.
    raw = props.get("qwr")
    if raw is None:
        return None, None, None
    try:
        return str(int(float(raw))), None, None
    except (TypeError, ValueError):
        return None, None, None


def _read_kolkata(props):
    return (props.get("WARD") or props.get("name") or "").strip() or None, None, None


def _read_osm(props):
    """Delhi and Ahmedabad, where no corporation ward file is published.

    These are OpenStreetMap admin levels 9-10, which in practice are revenue villages,
    colonies and sectors. Useful for orientation; deliberately labelled "Locality" so
    nobody quotes one as a ward number on a form.
    """
    return None, _titlecase(props.get("name")), None


READERS = {
    "chennai": _read_chennai,
    "mumbai": _read_mumbai,
    "bengaluru": _read_bengaluru,
    "hyderabad": _read_hyderabad,
    "pune": _read_pune,
    "kolkata": _read_kolkata,
}


def _resolve_polygon(store, layer_name, pt):
    """The polygon containing the point, else the nearest within tolerance."""
    layer = store.layer(layer_name)
    if not len(layer):
        return None, None
    hits = layer.containing(pt)
    if hits:
        return layer.props[hits[0]], "inside"
    idx, dist = layer.nearest(pt)
    if idx is not None and dist is not None and dist <= EDGE_TOLERANCE_M:
        return layer.props[idx], "edge"
    return None, None


def _chennai_zone(store, pt):
    props, _ = _resolve_polygon(store, "zones", pt)
    if not props:
        return None, None
    raw = props.get("ZONE_NAME")
    if not raw:
        return None, None
    zone = CHENNAI_ZONE_DISPLAY.get(raw.strip().upper(), _titlecase(raw))
    return zone, CHENNAI_ZONE_NUMBER.get(zone)


def _locality_only(city, store, pt, reader):
    """Nearest named locality, with no claim about corporation boundaries."""
    layer = store.layer("wards")
    name, distance = None, None
    if len(layer):
        idx, dist = layer.nearest(pt)
        if idx is not None and dist is not None and dist <= LOCALITY_RADIUS_M:
            _, name, _ = reader(layer.props[idx])
            distance = int(round(dist))

    if name:
        summary = name if (distance or 0) < 250 else "Near %s" % name
    else:
        summary = "%s does not publish ward boundaries" % city.corporation

    return {
        "city": city.slug,
        "city_name": city.name,
        "ward": name,
        "ward_number": None,
        "ward_name": name,
        "zone": None,
        "zone_number": None,
        "summary": summary,
        # Not a boundary claim either way, so this is not "outside the corporation".
        "inside_gcc": bool(name),
        "basis": "osm_locality",
        "ward_is_official": False,
        "nearest_zone": None,
        "nearest_zone_m": distance,
        "note": None,
    }


def resolve_administrative(city, lat, lng):
    """Ward and zone for a point.

    Returns nothing outside the corporation boundary rather than guessing at the nearest
    one, which would be actively misleading on a plot in an adjoining panchayat.
    """
    store = get_store(city)
    pt = point_utm(city, lat, lng)

    reader = READERS.get(city.slug, _read_osm)

    if city.slug in UNOFFICIAL_BOUNDARIES:
        return _locality_only(city, store, pt, reader)

    props, basis = _resolve_polygon(store, "wards", pt)
    ward_number, ward_name, zone = reader(props) if props else (None, None, None)

    zone_number = None
    if city.slug == "chennai" and (ward_number or basis):
        zone, zone_number = _chennai_zone(store, pt)

    inside = bool(ward_number or ward_name or zone)

    parts = []
    if ward_number and ward_name:
        parts.append("%s %s %s" % (city.ward_label, ward_number, ward_name))
    elif ward_number:
        parts.append("%s %s" % (city.ward_label, ward_number))
    elif ward_name:
        parts.append("%s %s" % (city.ward_label, ward_name))
    if zone:
        parts.append("%s %s %s" % (city.zone_label, zone_number, zone) if zone_number
                     else "%s %s" % (city.zone_label, zone))

    if inside:
        summary = ", ".join(parts)
    else:
        summary = "Outside the %s boundary" % city.corporation

    nearest_zone, nearest_zone_m = None, None
    if not inside:
        # A plot just outside the line is common on every city's fringe; naming what it
        # borders is more use to a buyer than a flat "outside".
        for layer_name in ("zones", "wards"):
            layer = store.layer(layer_name)
            if not len(layer):
                continue
            idx, dist = layer.nearest(pt)
            if idx is not None and dist is not None and dist <= 6000:
                _, name, zname = reader(layer.props[idx]) if layer_name == "wards" \
                    else (None, None, None)
                if layer_name == "zones" and city.slug == "chennai":
                    raw = layer.props[idx].get("ZONE_NAME")
                    name = CHENNAI_ZONE_DISPLAY.get((raw or "").strip().upper(), _titlecase(raw))
                nearest_zone = zname or name
                nearest_zone_m = int(round(dist))
                if nearest_zone:
                    summary = "Outside %s limits, %s from %s" % (
                        city.corporation,
                        "%dm" % nearest_zone_m if nearest_zone_m < 1000
                        else "%.1f km" % (nearest_zone_m / 1000.0),
                        nearest_zone)
                    break

    return {
        "city": city.slug,
        "city_name": city.name,
        "ward": ward_number or ward_name,
        "ward_number": ward_number,
        "ward_name": ward_name,
        "zone": zone,
        "zone_number": zone_number,
        "summary": summary,
        "inside_gcc": inside,
        "basis": basis,
        "nearest_zone": nearest_zone,
        "nearest_zone_m": nearest_zone_m,
        "ward_is_official": city.slug not in ("delhi", "ahmedabad"),
        "note": (None if inside else
                 "This plot has no %s ward. A panchayat or a neighbouring municipality "
                 "governs it, so building approvals, property tax and water connections "
                 "all run through a different office." % city.corporation),
    }
