"""Turning what people actually type into a point on the map.

Buyers search the way they speak - "velacheri", "anna nagar 2nd avenue", "near phoenix
mall", "OMR" - not in the administrative vocabulary (ward numbers, zone names, revenue
divisions) that official datasets are written in. Two things follow:

  * Query side: expand local shorthand before searching, and use a typo-tolerant
    geocoder. Nominatim returns nothing for "velacheri"; Photon returns Velachery.
  * Result side: never show government jargon back to the user. Nominatim labels look
    like "Mannady, Ward 60, Zone 5 Royapuram, Chennai Corporation, Chennai, Tamil Nadu,
    600079, India". Photon's own `locality` field carries things like "CMWSSB Division
    178". Both get stripped; we show "Mannady - Chennai 600079".
"""
import re

# National bounds. This used to be Chennai's box, which silently discarded every
# geocoding result in the other seven cities once the app went multi-city: the search
# returned 200 with zero results everywhere but Chennai. Per-city narrowing happens in
# the endpoint, against that city's own bbox.
LAT_MIN, LAT_MAX = 6.0, 36.0
LNG_MIN, LNG_MAX = 67.0, 98.0

CITY_CENTRE = (13.0827, 80.2707)  # default bias when no city is given

# Local shorthand that a geocoder will not resolve on its own. Applied as whole-word
# replacements before the query is sent.
ALIASES = {
    "omr": "Old Mahabalipuram Road",
    "ecr": "East Coast Road",
    "gst road": "Grand Southern Trunk Road",
    "gst": "Grand Southern Trunk Road",
    "mount road": "Anna Salai",
    "ltc": "Rajiv Gandhi Salai",
    "rajiv gandhi salai": "Rajiv Gandhi Salai",
    "poonamallee high road": "Poonamallee High Road",
    "phr": "Poonamallee High Road",
    "tnagar": "Thyagaraya Nagar",
    "t nagar": "Thyagaraya Nagar",
    "kk nagar": "K K Nagar",
    "vr mall": "VR Chennai",
    "marina": "Marina Beach",
}

# Filler that adds nothing to a geocoder query.
NOISE = re.compile(
    r"\b(near|nearby|close to|around|opposite|opp|behind|next to|beside|"
    r"plot|site|land|property|house|flat|apartment|for sale|in|at)\b",
    re.IGNORECASE)

# Administrative vocabulary that must never reach the user.
JARGON = re.compile(
    r"(ward\s*\d*|zone\s*\d*|division\s*\d*|cmwssb|corporation|municipality|"
    r"taluk|revenue|circle\s*\d*|panchayat|constituency)",
    re.IGNORECASE)

# Friendly names for OSM categories, so a result says "Street" not "highway/primary".
CATEGORY_LABELS = {
    "suburb": "Locality", "neighbourhood": "Locality", "quarter": "Locality",
    "city_district": "Locality", "village": "Locality", "town": "Locality",
    "city": "City", "hamlet": "Locality", "residential": "Locality",
    "station": "Station", "halt": "Station", "bus_stop": "Bus stop",
    "beach": "Beach", "hospital": "Hospital", "school": "School",
    "college": "College", "university": "University", "mall": "Mall",
    "supermarket": "Shop", "temple": "Temple", "place_of_worship": "Temple",
    "hotel": "Hotel", "restaurant": "Restaurant", "park": "Park",
    "traffic_signals": "Junction", "junction": "Junction",
}
STREET_KEYS = {"highway"}


def expand_query(raw):
    """Normalise a conversational query into something a geocoder can match."""
    text = " ".join(raw.strip().split())
    if not text:
        return text
    text = NOISE.sub(" ", text)
    text = " ".join(text.split())

    lowered = text.lower()
    for alias, full in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
        pattern = r"\b%s\b" % re.escape(alias)
        if re.search(pattern, lowered):
            text = re.sub(pattern, full, text, flags=re.IGNORECASE)
            lowered = text.lower()
    return " ".join(text.split())


def _clean(value):
    """Drop a field entirely if it is administrative jargon."""
    if not value:
        return None
    value = str(value).strip()
    if not value or JARGON.search(value):
        return None
    return value


def category_of(props):
    key = props.get("osm_key")
    value = props.get("osm_value")
    if key in STREET_KEYS:
        return "Street"
    if value in CATEGORY_LABELS:
        return CATEGORY_LABELS[value]
    if props.get("type") == "street":
        return "Street"
    if props.get("type") in ("city", "district"):
        return "Locality"
    if key in ("amenity", "shop", "leisure", "tourism", "building", "office"):
        return "Landmark"
    return "Place"


def build_label(props):
    """(primary, context) - what the user reads, with no ward/zone vocabulary.

    Primary is the thing they searched for; context places it well enough to tell two
    similarly named results apart.
    """
    name = _clean(props.get("name"))
    street = _clean(props.get("street"))
    district = _clean(props.get("district"))
    city = _clean(props.get("city")) or _clean(props.get("county"))
    postcode = props.get("postcode")

    primary = name or street or district or city or "Unnamed place"

    parts = []
    for candidate in (street, district, city):
        if candidate and candidate != primary and candidate not in parts:
            parts.append(candidate)
    # "Chennai" twice reads badly when district is already a Chennai neighbourhood.
    context = ", ".join(parts[:2])
    if postcode and str(postcode).isdigit():
        context = ("%s %s" % (context, postcode)).strip()
    return primary, context


# Words that appear in half the place names in Chennai. They say what kind of thing a
# result is, not which one, so they must not outvote the distinctive part of a query.
GENERIC_TOKENS = {
    "road", "street", "st", "nagar", "chennai", "main", "cross", "avenue", "ave",
    "high", "colony", "extension", "phase", "block", "sector", "north", "south",
    "east", "west", "new", "old", "salai", "lane", "garden", "gardens", "puram",
    "station", "railway", "bus", "stop", "metro", "mrts", "junction", "signal",
    "temple", "church", "mosque", "school", "college", "hospital", "mall", "market",
}

# When someone types "railway station" they want a station, not a police station that
# happens to share the words. Map intent words onto the categories we assign.
INTENT_CATEGORIES = {
    "station": {"Station"}, "railway": {"Station"}, "metro": {"Station"},
    "mrts": {"Station"}, "train": {"Station"},
    "bus": {"Bus stop"}, "stop": {"Bus stop"},
    "mall": {"Mall"}, "beach": {"Beach"}, "temple": {"Temple"},
    "hospital": {"Hospital"}, "park": {"Park"},
    "junction": {"Junction"}, "signal": {"Junction"},
}


def _tokens(text):
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]


def _similarity(a, b):
    """Prefix-overlap ratio, which survives the transliteration wobble in Chennai names.

    "thiruvanmiyur" and "thiruvanmyur" are the same place spelled two ways; they share a
    nine-character prefix, so this scores them close without a full edit-distance pass.
    """
    if a == b:
        return 1.0
    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
        return 0.9
    shared = 0
    for x, y in zip(a, b):
        if x != y:
            break
        shared += 1
    longest = max(len(a), len(b))
    if longest < 4 or shared < 4:
        return 0.0
    ratio = shared / longest
    return ratio if ratio >= 0.6 else 0.0


def relevance(query, label, context, category):
    """How well a result answers the query. Higher is better.

    Photon ranks "Perambur Loco Works Railway Station" above everything for
    "thiruvanmiyur railway station", because the generic words match perfectly and the
    one word that matters does not. This re-weights toward the distinctive tokens.
    """
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    label_tokens = _tokens(label)
    context_tokens = _tokens(context)

    score = 0.0
    for token in query_tokens:
        weight = 0.25 if token in GENERIC_TOKENS else 1.0
        best_label = max((_similarity(token, t) for t in label_tokens), default=0.0)
        best_context = max((_similarity(token, t) for t in context_tokens), default=0.0)
        score += weight * max(best_label * 2.0, best_context * 1.0)

        wanted = INTENT_CATEGORIES.get(token)
        if wanted and category in wanted:
            score += 0.75

    return score


def split_anchor(query):
    """Split "velacheri bus stop" into ("velacheri", "bus stop").

    Returns (area_part, type_part) when the query names a place *and* a kind of thing,
    otherwise (None, None). Used to resolve the area first and search near it, because
    a plain search for "velacheri bus stop" returns bus stops all over the city.
    """
    tokens = _tokens(query)
    if len(tokens) < 2:
        return None, None
    area = [t for t in tokens if t not in GENERIC_TOKENS]
    kind = [t for t in tokens if t in GENERIC_TOKENS]
    if not area or not kind:
        return None, None
    return " ".join(area), " ".join(kind)


def in_region(lat, lng, bbox=None):
    """Inside the given city's bbox (with slack for fringe plots), else inside India."""
    if bbox is not None:
        lat_min, lng_min, lat_max, lng_max = bbox
        pad = 0.25
        return (lat_min - pad <= lat <= lat_max + pad
                and lng_min - pad <= lng <= lng_max + pad)
    return LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX
