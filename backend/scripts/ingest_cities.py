"""Download the municipal datasets that exist for cities beyond Chennai.

Coverage is thin and uneven. This script downloads only what each corporation actually
publishes on OpenCity; a city with nothing here still gets a score from OpenStreetMap
and SRTM terrain, and says so.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.ingest_kml import RAW_DIR, PROCESSED_DIR, convert, download  # noqa: E402

BASE = "https://data.opencity.in/dataset"

SOURCES = {
    # --- ward and zone boundaries -------------------------------------------------
    "mumbai_wards": {
        "url": BASE + "/60f27371-717e-40b6-8554-fdc7e6c10437/resource/"
                      "0318c3e8-1530-4bf4-b29b-7281573dee8a/download/"
                      "e7a671e2-1f71-4219-a83c-556334bc9021.kml",
        "keep": ["name", "Name", "WARD", "ward"],
    },
    "bengaluru_wards": {
        "url": BASE + "/87b978d1-352e-4b90-aa2c-9991e55d3425/resource/"
                      "4dd58225-3ad2-4a99-9003-4e8d71e7f99f/download/"
                      "e56d21e8-0c44-4c35-9e5d-c732f6f59c97.kml",
        "keep": ["name_en", "proposed_ward_name_en", "id", "ward_area", "population"],
    },
    "hyderabad_wards": {
        "url": BASE + "/15cb7d8d-eed1-4aad-8cd7-f281cbf4f94f/resource/"
                      "14b033e3-3721-4149-8326-cc29420e062e/download/ghmc_wards.kml",
        "keep": ["ward", "CIRCLE", "ZONE", "AREA_IN_SQ"],
    },
    "hyderabad_zones": {
        "url": BASE + "/15cb7d8d-eed1-4aad-8cd7-f281cbf4f94f/resource/"
                      "ecaab873-4dd3-42db-9813-b9c28b45ca68/download/"
                      "28fc477d-7725-4d57-8941-620f02a6a8dd.kml",
        "keep": ["name", "Name", "ZONE", "ZONE_NAME", "zone"],
    },
    "pune_wards": {
        "url": BASE + "/98f28dac-9158-46ee-a91e-a514d9af427c/resource/"
                      "2badcc86-489c-4b7e-b7dd-a273ef01b798/download/"
                      "b7a3f392-238c-4c55-a3ed-0c13fd4aaa0a.kml",
        # This file carries only "qwr", the prabhag number as a float. There is no
        # name field in PMC's published electoral ward map.
        "keep": ["qwr"],
    },
    "kolkata_wards": {
        "url": BASE + "/e1c4f558-eff2-44c3-b703-d9d6ea45c577/resource/"
                      "b3195f54-6c85-4cb4-afa0-06af482fe9df/download/"
                      "10f7cc2f-5005-412f-861d-d5e085dd92fb.kml",
        "keep": ["name", "Name", "WARD", "ward_no", "BOROUGH"],
    },

    # --- Bengaluru is the only other city with real flood and drain data ----------
    "bengaluru_swd": {
        "url": BASE + "/fc97e05c-c54b-44e9-8d98-7663ee887922/resource/"
                      "801779e6-ed81-457d-bd2a-7e3cc95ad1ee/download/"
                      "e42be0cb-1bf4-4a7b-9c78-0c0dbdae3237.kml",
        "keep": ["name", "Name", "TYPE", "WIDTH", "STATUS", "DRAIN_TYPE"],
    },
    "bengaluru_flood_points": {
        "url": BASE + "/b03218ea-4b7c-4fa9-ab67-b9054d7ecc4c/resource/"
                      "d90fe768-caba-4c6e-b6b5-a75acd5e88a9/download/"
                      "00fb1229-dcfd-4f59-813f-885e0c629add.kml",
        "keep": ["name", "Name", "location", "Ward"],
    },
    "bengaluru_low_lying": {
        "url": BASE + "/b03218ea-4b7c-4fa9-ab67-b9054d7ecc4c/resource/"
                      "62ceac3b-f6e2-4dd1-ae9f-be80b1f2fda8/download/"
                      "8e87a2fc-e014-4c6e-81f1-d5cb4db57a46.kml",
        "keep": ["name", "Name", "location", "Ward", "AREA"],
    },
    "bengaluru_groundwater": {
        "url": BASE + "/7d08569b-8e7e-45ff-b261-93ad4d8f9d17/resource/"
                      "54f984c6-3f18-4e51-96ef-1f00b7129562/download/"
                      "2b2e95fb-23f0-4351-b06a-f75ac81dc8c0.kml",
        # Measured well depths, 2007-2013. Better evidence than anything curated.
        "keep": ["code", "mdy", "depth_in_m", "Info"],
    },

    # --- municipal water, where the corporation publishes better than OSM ---------
    # These arrived after Overpass started refusing connections mid-build, and several
    # are better than the OSM equivalent anyway: a water census beats crowd-mapping.
    "delhi_waterbodies": {
        "url": BASE + "/0e089da2-53bc-4751-a919-7d6f95f72784/resource/"
                      "0d3882a6-4d4e-4d67-87fc-d23729b1f6eb/download/"
                      "b4219512-7105-4227-9c95-9bdf64020799.kml",
        "keep": ["name", "Name", "TYPE", "type", "AREA"],
    },
    "kolkata_waterbodies": {
        "url": BASE + "/d9c9b5e1-01e2-4fa4-8c7c-ff335d327f96/resource/"
                      "8b4faaae-746e-4079-8d08-93c54fa04956/download/"
                      "bdb7e96d-acaf-442c-9488-b9f8297404ca.kml",
        "keep": ["name", "Name", "TYPE", "type", "AREA"],
    },
    "pune_waterbodies": {
        "url": BASE + "/a83b2053-2250-4e3c-9759-521c81679d24/resource/"
                      "7507f222-3bcd-4881-b558-90c5cbc2625f/download/"
                      "b0d9ef1f-14d7-4c93-a498-3ffb7c86737c.kml",
        "keep": ["name", "Name", "RIVER", "type"],
    },
    "pune_swd": {
        "url": BASE + "/a83b2053-2250-4e3c-9759-521c81679d24/resource/"
                      "b9bdda98-a0d1-4e2e-aca3-36c6445751b5/download/"
                      "3f7228b1-092e-4c66-a62f-6895cf33fbcd.kml",
        "keep": ["name", "Name", "TYPE", "WIDTH", "NALLA"],
    },

    # --- Hyderabad ----------------------------------------------------------------
    "hyderabad_flood_points": {
        "url": BASE + "/fbc0cf2e-2c10-4d9a-8dfd-0b1c24c6f279/resource/"
                      "8ab584c9-19ca-4c1b-945f-f19fe1db5de5/download/"
                      "d6d078ca-7330-4efe-8a5f-0c74cb6a0a70.kml",
        "keep": ["name", "Name", "location", "Circle", "Zone"],
    },
}


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    ok, failed = 0, []
    for name, spec in SOURCES.items():
        print("[%s]" % name)
        try:
            kml = download(name, spec["url"])
            convert(name, kml, set(spec["keep"]))
            ok += 1
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the rest
            print("  ! failed: %s" % exc)
            failed.append(name)
    print("\n%d of %d downloaded" % (ok, len(SOURCES)))
    if failed:
        print("failed: %s" % ", ".join(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
