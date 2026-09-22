"""The cities this tool covers, and how much is actually known about each one.

Coverage is wildly uneven across India, and pretending otherwise would be the most
dangerous thing this tool could do. Chennai has 7,453 GCC flood-inundation polygons that
I validated against recorded flooding. No other city publishes anything comparable:
Bengaluru has low-lying areas and drains, Hyderabad has flooding points, and the rest
have nothing beyond terrain and OpenStreetMap.

So every city declares what backs it. `depth` drives the confidence the API reports and
the wording the report uses, and `scoreable_dimensions` decides which of the three risks
can honestly be graded at all. A dimension with no data behind it is dropped from the
composite and the remaining weights are renormalised, rather than filled with a guess.
"""

WGS84 = "EPSG:4326"


class City:
    def __init__(self, slug, name, state, corporation, centre, bbox, epsg,
                 depth, layers, ward_label="Ward", zone_label="Zone", notes=None):
        self.slug = slug
        self.name = name
        self.state = state
        self.corporation = corporation
        self.centre = centre          # (lat, lng)
        self.bbox = bbox              # (lat_min, lng_min, lat_max, lng_max)
        self.epsg = epsg              # metric CRS for this city's longitude
        self.depth = depth            # deep | moderate | baseline
        self.layers = layers          # logical name -> processed filename
        self.ward_label = ward_label
        self.zone_label = zone_label
        self.notes = notes or {}

    @property
    def utm(self):
        return "EPSG:%d" % self.epsg

    def has(self, layer):
        return layer in self.layers

    @property
    def scoreable_dimensions(self):
        """Which risks this city has any real data for."""
        # Flood always has terrain behind it. Contamination needs a mapped industrial
        # or waste layer; scarcity needs groundwater evidence. Both are dropped rather
        # than zeroed where the city publishes nothing.
        dims = ["flood"]
        if self.has("industrial") or self.slug == "chennai":
            dims.append("contamination")
        # Chennai's groundwater comes from a curated point file rather than a GeoJSON
        # layer; Bengaluru has 1,114 measured well depths. Nowhere else has anything, and
        # the dimension is dropped rather than guessed.
        if self.slug == "chennai" or self.has("groundwater"):
            dims.append("scarcity")
        return dims

    def contains(self, lat, lng):
        lat_min, lng_min, lat_max, lng_max = self.bbox
        return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max

    def to_dict(self):
        return {
            "slug": self.slug,
            "name": self.name,
            "state": self.state,
            "corporation": self.corporation,
            "centre": {"lat": self.centre[0], "lng": self.centre[1]},
            "bbox": {"lat_min": self.bbox[0], "lng_min": self.bbox[1],
                     "lat_max": self.bbox[2], "lng_max": self.bbox[3]},
            "depth": self.depth,
            "layers": sorted(self.layers.keys()),
            "scoreable_dimensions": self.scoreable_dimensions,
            "ward_label": self.ward_label,
            "zone_label": self.zone_label,
            "notes": self.notes,
        }


def _f(slug, *names):
    """Processed-file names for a city's layers."""
    return {n: "%s_%s.geojson" % (slug, n) for n in names}


CITIES = {}


def _add(city):
    CITIES[city.slug] = city
    return city


# UTM zone follows longitude: 43N covers 72-78E, 44N covers 78-84E, 45N covers 84-90E.
# Using the right one keeps every distance in this app a true metre.

_add(City(
    "chennai", "Chennai", "Tamil Nadu", "Greater Chennai Corporation",
    centre=(13.0827, 80.2707), bbox=(12.70, 79.90, 13.40, 80.45), epsg=32644,
    depth="deep",
    layers=dict(
        # Chennai was ingested before the multi-city naming scheme, so its files keep
        # their original names rather than being renamed for cosmetic consistency.
        waterbodies="osm_waterbodies.geojson",
        industrial="osm_industrial.geojson",
        landfill="osm_landfill.geojson",
        coastline="osm_coastline.geojson",
        flood_zones="flood_hazard_zones.geojson",
        flood_hotspots="flood_hotspots_2020.geojson",
        swd="swd_network.geojson",
        wards="gcc_wards_2022.geojson",
        zones="gcc_zones_2022.geojson",
    ),
    notes={"flood": "GCC inundation survey: 7,453 graded polygons, validated against "
                    "the 53 recorded 2020 hotspots (High+Very High cover 10.8% of the "
                    "area and contain 45% of them)."},
))

_add(City(
    "bengaluru", "Bengaluru", "Karnataka", "BBMP",
    centre=(12.9716, 77.5946), bbox=(12.80, 77.40, 13.18, 77.80), epsg=32643,
    depth="moderate",
    layers=dict(
        _f("bengaluru", "waterbodies", "industrial", "landfill"),
        flood_hotspots="bengaluru_flood_points.geojson",
        low_lying="bengaluru_low_lying.geojson",
        swd="bengaluru_swd.geojson",
        wards="bengaluru_wards.geojson",
        groundwater="bengaluru_groundwater.geojson",
    ),
    notes={"flood": "BBMP flood-prone locations and low-lying areas, plus the BBMP "
                    "stormwater drain network. No graded inundation survey is published, "
                    "so terrain carries more of the score than it does in Chennai."},
))

_add(City(
    "hyderabad", "Hyderabad", "Telangana", "GHMC",
    centre=(17.3850, 78.4867), bbox=(17.18, 78.20, 17.62, 78.70), epsg=32644,
    depth="moderate",
    layers=dict(
        _f("hyderabad", "waterbodies", "industrial", "landfill"),
        flood_hotspots="hyderabad_flood_points.geojson",
        wards="hyderabad_wards.geojson",
        zones="hyderabad_zones.geojson",
    ),
    notes={"flood": "GHMC flooding points only. No inundation survey is published, so "
                    "the score leans on terrain and water proximity."},
))

_add(City(
    "mumbai", "Mumbai", "Maharashtra", "BMC (MCGM)",
    centre=(19.0760, 72.8777), bbox=(18.85, 72.74, 19.32, 73.12), epsg=32643,
    depth="baseline",
    layers=dict(
        _f("mumbai", "waterbodies", "industrial", "landfill", "coastline"),
        wards="mumbai_wards.geojson",
    ),
    ward_label="Ward",
    notes={"flood": "No municipal flood survey is openly published for Mumbai. The "
                    "flood score here rests on terrain, water proximity and the coast."},
))

_add(City(
    "delhi", "Delhi", "Delhi", "MCD / NDMC",
    centre=(28.6139, 77.2090), bbox=(28.35, 76.80, 28.92, 77.40), epsg=32643,
    depth="baseline",
    layers=_f("delhi", "waterbodies", "industrial", "landfill", "wards"),
    # MCD does not publish ward boundaries openly, so these come from OpenStreetMap
    # admin levels 9-10, which in Delhi are revenue villages, colonies and sectors -
    # useful for orientation, but not the ward number that appears on paperwork.
    ward_label="Locality",
    notes={"flood": "No municipal flood survey is openly published. Terrain, the Yamuna "
                    "and mapped water carry the score.",
           "wards": "MCD ward boundaries are not openly published. The locality shown "
                    "comes from OpenStreetMap and is not the MCD ward number."},
))

_add(City(
    "pune", "Pune", "Maharashtra", "PMC",
    centre=(18.5204, 73.8567), bbox=(18.38, 73.66, 18.68, 74.02), epsg=32643,
    depth="baseline",
    ward_label="Prabhag",
    layers=dict(
        _f("pune", "waterbodies", "industrial", "landfill"),
        swd="pune_swd.geojson",       # PMC nalla network
        wards="pune_wards.geojson",
    ),
    notes={"flood": "No municipal flood survey is openly published. Terrain and the "
                    "Mula-Mutha river system carry the score."},
))

_add(City(
    "kolkata", "Kolkata", "West Bengal", "KMC",
    centre=(22.5726, 88.3639), bbox=(22.40, 88.22, 22.78, 88.52), epsg=32645,
    depth="baseline",
    layers=dict(
        _f("kolkata", "waterbodies", "industrial", "landfill"),
        wards="kolkata_wards.geojson",
    ),
    notes={"flood": "No municipal flood survey is openly published. Kolkata sits on a "
                    "deltaic plain with very little relief, so terrain separates plots "
                    "less here than in other cities."},
))

_add(City(
    "ahmedabad", "Ahmedabad", "Gujarat", "AMC",
    centre=(23.0225, 72.5714), bbox=(22.93, 72.42, 23.18, 72.75), epsg=32643,
    depth="baseline",
    layers=_f("ahmedabad", "waterbodies", "industrial", "landfill", "wards"),
    ward_label="Locality",
    notes={"flood": "No municipal flood survey is openly published. Terrain and the "
                    "Sabarmati carry the score.",
           "wards": "AMC ward boundaries are not openly published. The locality shown "
                    "comes from OpenStreetMap and is not the AMC ward number."},
))

DEFAULT_CITY = "chennai"


def get(slug):
    return CITIES.get((slug or "").strip().lower())


def find_by_point(lat, lng):
    """Which city covers this point? Falls back to the nearest centre when none does."""
    for city in CITIES.values():
        if city.contains(lat, lng):
            return city
    return None


def nearest(lat, lng):
    import math
    best, best_d = None, None
    for city in CITIES.values():
        d = math.hypot(city.centre[0] - lat, (city.centre[1] - lng) * math.cos(math.radians(lat)))
        if best_d is None or d < best_d:
            best, best_d = city, d
    return best, best_d
