"""Emit the manually curated datasets that have no machine-readable public API.

Provenance is tracked per record so the scoring engine never presents a flagged
locality as if it carried a measured index:

  cpcb_cepi      - numeric CEPI published by CPCB / cited in the project brief
  locality_flag  - named as high risk in the project brief, no numeric index
  cgwb_cited     - groundwater level cited in the project brief
  cgwb_regional  - inferred from the CGWB regional finding that 46 of 51 Chennai
                   revenue blocks are overexploited and only 2 firkas are safe
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANUAL_DIR = os.path.join(ROOT, "data", "manual")

INDUSTRIAL_CLUSTERS = [
    {"name": "Manali Industrial Area", "lat": 13.1647, "lng": 80.2587, "radius_m": 3000,
     "cepi_score": 78.44, "pollution_level": "critically_polluted", "provenance": "cpcb_cepi",
     "sources": "Petrochemicals, refineries, fertilisers, thermal power",
     "note": "68% of groundwater samples exceed Heavy Metal Pollution Index 100; ~300 units."},
    {"name": "Ambattur Industrial Estate", "lat": 13.1143, "lng": 80.1548, "radius_m": 2000,
     "cepi_score": 52.0, "pollution_level": "severely_polluted", "provenance": "cpcb_cepi",
     "sources": "Manufacturing, chemicals, plastics"},
    {"name": "Chromepet / Pallavaram tannery belt", "lat": 12.9516, "lng": 80.1462, "radius_m": 1500,
     "cepi_score": 45.0, "pollution_level": "polluted", "provenance": "cpcb_cepi",
     "sources": "Tanneries (legacy), leather processing",
     "note": "Chromium legacy contamination in shallow aquifer."},
    {"name": "Ennore industrial / thermal belt", "lat": 13.2167, "lng": 80.3167, "radius_m": 3000,
     "cepi_score": None, "pollution_level": "critically_polluted", "provenance": "locality_flag",
     "sources": "Thermal power, coal ash ponds, port and petrochemical handling",
     "note": "Fly-ash slurry and Kosasthalaiyar backwater contamination."},
    {"name": "Pammal industrial cluster", "lat": 12.9675, "lng": 80.1300, "radius_m": 1200,
     "cepi_score": None, "pollution_level": "polluted", "provenance": "locality_flag",
     "sources": "Tanneries, small-scale chemical units"},
    {"name": "Velappanchavadi industrial belt", "lat": 13.0500, "lng": 80.1300, "radius_m": 1200,
     "cepi_score": None, "pollution_level": "polluted", "provenance": "locality_flag",
     "sources": "Small-scale manufacturing, dyeing units"},
    {"name": "Madhavaram industrial area", "lat": 13.1500, "lng": 80.2300, "radius_m": 1500,
     "cepi_score": None, "pollution_level": "polluted", "provenance": "locality_flag",
     "sources": "Petroleum storage terminals, oil depots"},
]

DUMPSITES = [
    {"name": "Perungudi Dumpyard", "lat": 12.9576, "lng": 80.2422, "active": True,
     "leachate_radius_m": 2000, "provenance": "locality_flag",
     "note": "Leachate seeps into the Pallikaranai marsh aquifer."},
    {"name": "Kodungaiyur Dumpyard", "lat": 13.1326, "lng": 80.2524, "active": True,
     "leachate_radius_m": 2000, "provenance": "locality_flag",
     "note": "Chennai's largest legacy dumpsite; north Chennai aquifer impact."},
]

# CGWB / CMWSSB groundwater exploitation status.
#
# Two important caveats, both surfaced in the API response:
#  * Published firka *boundary polygons* are not openly downloadable, so each unit is
#    a locality centroid with an influence radius, not a real administrative boundary.
#  * Only the four "cgwb_cited" records carry a water level from a published source.
#    The rest are marked "cgwb_regional": CGWB reports 46 of Chennai's 51 revenue
#    blocks as overexploited with only Puzhal and Sholinganallur safe, which supports
#    treating an unlisted Chennai locality as overexploited - but the engine flags
#    these as medium confidence rather than asserting a measured figure.
def _regional(name, lat, lng, radius_m=2500, classification="overexploited"):
    return {"firka": name, "lat": lat, "lng": lng, "radius_m": radius_m,
            "classification": classification, "avg_gw_level_m": None,
            "provenance": "cgwb_regional", "unit": "locality_proxy"}


GROUNDWATER_FIRKAS = [
    {"firka": "Puzhal", "lat": 13.1600, "lng": 80.1900, "radius_m": 4000,
     "classification": "safe", "avg_gw_level_m": 2.5, "provenance": "cgwb_cited",
     "unit": "locality_proxy"},
    {"firka": "Sholinganallur", "lat": 12.9010, "lng": 80.2279, "radius_m": 4000,
     "classification": "safe", "avg_gw_level_m": 3.1, "provenance": "cgwb_cited",
     "unit": "locality_proxy"},
    {"firka": "Virugambakkam", "lat": 13.0500, "lng": 80.1900, "radius_m": 3000,
     "classification": "overexploited", "avg_gw_level_m": 12.0, "provenance": "cgwb_cited",
     "unit": "locality_proxy"},
    {"firka": "Medavakkam", "lat": 12.9200, "lng": 80.1900, "radius_m": 3500,
     "classification": "overexploited", "avg_gw_level_m": 8.5, "provenance": "cgwb_cited",
     "unit": "locality_proxy"},
] + [
    _regional("Adyar", 13.0067, 80.2570),
    _regional("Adambakkam", 12.9880, 80.2020),
    _regional("Alandur", 13.0027, 80.2000),
    _regional("Ambattur", 13.1143, 80.1548, 3000),
    _regional("Aminjikarai", 13.0730, 80.2220),
    _regional("Anna Nagar", 13.0850, 80.2101),
    _regional("Ashok Nagar", 13.0350, 80.2100),
    _regional("Avadi", 13.1147, 80.1098, 4000),
    _regional("Besant Nagar", 13.0002, 80.2668),
    _regional("Chitlapakkam", 12.9250, 80.1400),
    _regional("Choolaimedu", 13.0620, 80.2250),
    _regional("Chromepet", 12.9516, 80.1462),
    _regional("Egmore", 13.0732, 80.2609),
    _regional("Ennore", 13.2167, 80.3167, 3500),
    _regional("Guduvancheri", 12.8450, 80.0600, 4500),
    _regional("Injambakkam", 12.9280, 80.2500),
    _regional("Kelambakkam", 12.7900, 80.2200, 4000),
    _regional("Kodambakkam", 13.0500, 80.2270),
    _regional("Kolathur", 13.1200, 80.2100),
    _regional("Korattur", 13.1050, 80.1850),
    _regional("Kotturpuram", 13.0150, 80.2450),
    _regional("Kundrathur", 12.9950, 80.0950, 4000),
    _regional("Madhavaram", 13.1500, 80.2300, 3000),
    _regional("Madipakkam", 12.9630, 80.1990),
    _regional("Manali", 13.1647, 80.2587, 3000),
    _regional("Manapakkam", 13.0150, 80.1750),
    _regional("Minjur", 13.2800, 80.2600, 4000),
    _regional("Mogappair", 13.0850, 80.1750),
    _regional("Mudichur", 12.9080, 80.0700, 3500),
    _regional("Mylapore", 13.0339, 80.2698),
    _regional("Nanganallur", 12.9820, 80.1900),
    _regional("Navalur", 12.8450, 80.2270, 3000),
    _regional("Nungambakkam", 13.0569, 80.2425),
    _regional("Pallavaram", 12.9675, 80.1491),
    _regional("Pallikaranai", 12.9400, 80.2100),
    _regional("Pammal", 12.9675, 80.1300),
    _regional("Perambur", 13.1070, 80.2340),
    _regional("Perumbakkam", 12.9060, 80.2050),
    _regional("Perungudi", 12.9576, 80.2422),
    _regional("Poonamallee", 13.0480, 80.0950, 4000),
    _regional("Porur", 13.0359, 80.1567, 3000),
    _regional("Purasawalkam", 13.0900, 80.2500),
    _regional("Red Hills", 13.1900, 80.1800, 3500),
    _regional("Royapuram", 13.1100, 80.2930),
    _regional("Saidapet", 13.0210, 80.2230),
    _regional("Selaiyur", 12.9100, 80.1400),
    _regional("Siruseri", 12.8250, 80.2200, 3000),
    _regional("Sunnambu Kolathur", 12.9330, 80.1870),
    _regional("T Nagar", 13.0418, 80.2341),
    _regional("Tambaram", 12.9229, 80.1275, 4000),
    _regional("Thiruvanmiyur", 12.9830, 80.2590),
    _regional("Thiruvottiyur", 13.1600, 80.3000, 3000),
    _regional("Thoraipakkam", 12.9250, 80.2280),
    _regional("Tondiarpet", 13.1300, 80.2900),
    _regional("Triplicane", 13.0570, 80.2760),
    _regional("Vadapalani", 13.0500, 80.2120),
    _regional("Velachery", 12.9783, 80.2209),
    _regional("Villivakkam", 13.1030, 80.2100),
    _regional("Washermanpet", 13.1150, 80.2830),
    _regional("West Mambalam", 13.0400, 80.2200),
]

# Localities the brief names as historically flood-prone. Used only to add narrative
# context to a report - never to move the numeric flood score, which comes from the
# GCC inundation polygons.
FLOOD_CONTEXT_LOCALITIES = [
    {"name": "Velachery", "lat": 12.9783, "lng": 80.2209, "radius_m": 2500,
     "note": "Built substantially on the former Velachery lake bed and marsh fringe."},
    {"name": "Mudichur", "lat": 12.9080, "lng": 80.0700, "radius_m": 2500,
     "note": "Adyar river overflow path; severe 2015 inundation."},
    {"name": "Madipakkam", "lat": 12.9630, "lng": 80.1990, "radius_m": 2000,
     "note": "Low-lying, drains into the Pallikaranai marsh."},
    {"name": "Perumbakkam", "lat": 12.9060, "lng": 80.2050, "radius_m": 2500,
     "note": "Marsh-edge development, poor drain connectivity."},
    {"name": "Sunnambu Kolathur", "lat": 12.9330, "lng": 80.1870, "radius_m": 2000,
     "note": "Former waterbody catchment."},
    {"name": "Pallikaranai", "lat": 12.9400, "lng": 80.2100, "radius_m": 3000,
     "note": "Ramsar-listed marsh; the city's principal flood sink, heavily encroached."},
    {"name": "Thoraipakkam - Siruseri OMR corridor", "lat": 12.9250, "lng": 80.2280, "radius_m": 4000,
     "note": "IT corridor built across the marsh drainage path."},
    {"name": "Vyasarpadi", "lat": 13.1150, "lng": 80.2550, "radius_m": 2000,
     "note": "Cooum and Buckingham Canal overflow zone."},
    {"name": "Kodungaiyur", "lat": 13.1326, "lng": 80.2524, "radius_m": 2000,
     "note": "Low-lying north Chennai basin."},
    {"name": "Ennore", "lat": 13.2167, "lng": 80.3167, "radius_m": 3000,
     "note": "Kosasthalaiyar backwater and creek flooding."},
    {"name": "Mylapore - Adyar river basin", "lat": 13.0100, "lng": 80.2550, "radius_m": 2500,
     "note": "Adyar tidal reach."},
]

DATASETS = {
    "industrial_clusters.json": INDUSTRIAL_CLUSTERS,
    "dumpsites.json": DUMPSITES,
    "groundwater_firkas.json": GROUNDWATER_FIRKAS,
    "flood_context_localities.json": FLOOD_CONTEXT_LOCALITIES,
}


def main():
    os.makedirs(MANUAL_DIR, exist_ok=True)
    for filename, payload in DATASETS.items():
        path = os.path.join(MANUAL_DIR, filename)
        with open(path, "w") as fh:
            json.dump(payload, fh, indent=2)
        print("  -> %s (%d records)" % (path, len(payload)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
