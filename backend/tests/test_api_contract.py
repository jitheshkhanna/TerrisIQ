"""QA suite: invariants and edge cases, not just happy paths."""
import json, sys, urllib.error, urllib.parse, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
FAILS, WARNS, PASSES = [], [], 0


def check(name, condition, detail=""):
    global PASSES
    if condition:
        PASSES += 1
    else:
        FAILS.append("%s -- %s" % (name, detail))


def warn(name, detail=""):
    WARNS.append("%s -- %s" % (name, detail))


def post(path, payload, timeout=120):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"err": str(e)}


def get(path, timeout=120):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            ct = r.headers.get("Content-Type", "")
            body = r.read()
            return r.status, (json.loads(body) if "json" in ct else body)
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"err": str(e)}


print("=" * 78)
print("QA against %s" % BASE)
print("=" * 78)

# ---------- 1. city registry ----------
st, cities = get("/api/v1/cities")
check("cities endpoint 200", st == 200, "got %s" % st)
slugs = [c["slug"] for c in cities.get("cities", [])]
check("8 cities listed", len(slugs) == 8, "got %d: %s" % (len(slugs), slugs))

CENTRES = {c["slug"]: (c["centre"]["lat"], c["centre"]["lng"]) for c in cities.get("cities", [])}

# ---------- 2. every city scores at its own centre ----------
for slug, (lat, lng) in CENTRES.items():
    st, d = post("/api/v1/risk", {"latitude": lat, "longitude": lng, "city": slug})
    check("%s scores" % slug, st == 200, "status %s" % st)
    if st != 200:
        continue
    s = d["composite_score"]
    check("%s score in 0-100" % slug, 0 <= s <= 100, "got %s" % s)
    check("%s grade valid" % slug, d["composite_grade"] in "ABCDF", d["composite_grade"])
    w = d["weights"]
    check("%s weights sum to 1" % slug, abs(sum(w.values()) - 1.0) < 1e-6, str(w))
    check("%s city echoed" % slug, d["city"]["slug"] == slug, d["city"]["slug"])
    # plain-language verdict replaces letter grades on screen
    check("%s verdict present" % slug, d.get("verdict") in
          ("Very low risk", "Low risk", "Moderate risk", "High risk", "Very high risk"),
          str(d.get("verdict")))
    check("%s level 1-5" % slug, d.get("level") in (1, 2, 3, 4, 5), str(d.get("level")))
    for dim in ("flood", "contamination", "scarcity"):
        blk = d.get(dim)
        if not blk:
            continue
        check("%s %s has facts" % (slug, dim), len(blk.get("facts", [])) > 0, "no facts")
        for f in blk.get("facts", []):
            check("%s %s fact <=6 words" % (slug, dim), len(f["text"].split()) <= 6, f["text"])
            check("%s %s fact level valid" % (slug, dim),
                  f["level"] in ("high", "medium", "low", "good", "info"), f["level"])
    # every scored dimension must be present; every unavailable one must be null
    for dim in ("flood", "contamination", "scarcity"):
        if dim in d["unavailable_dimensions"]:
            check("%s %s is null when unavailable" % (slug, dim), d[dim] is None, "not null")
            check("%s %s absent from weights" % (slug, dim), dim not in w, "in weights")
        else:
            check("%s %s present" % (slug, dim), d[dim] is not None, "is null")

# ---------- 3. grade band boundaries ----------
sys.path.insert(0, ".")
from app.core.scoring import compute_grade
for score, expected in [(0,"A"),(20,"A"),(21,"B"),(40,"B"),(41,"C"),(60,"C"),
                        (61,"D"),(80,"D"),(81,"F"),(100,"F")]:
    g, _ = compute_grade(score)
    check("grade(%d)==%s" % (score, expected), g == expected, "got %s" % g)

# ---------- 4. input validation ----------
st, _ = post("/api/v1/risk", {"latitude": 200, "longitude": 80})
check("rejects lat 200", st == 422, "got %s" % st)
st, _ = post("/api/v1/risk", {"latitude": 13.0, "longitude": 500})
check("rejects lng 500", st == 422, "got %s" % st)
st, _ = post("/api/v1/risk", {"latitude": 13.0})
check("rejects missing lng", st == 422, "got %s" % st)
st, d = post("/api/v1/risk", {"latitude": 13.0827, "longitude": 80.2707, "city": "atlantis"})
check("rejects unknown city", st == 404, "got %s" % st)
# a point far from every covered city
st, d = post("/api/v1/risk", {"latitude": 26.9124, "longitude": 75.7873})  # Jaipur
check("uncovered point refused", st == 422, "got %s (%s)" % (st, str(d)[:70]))

# ---------- 5. city/coordinate mismatch ----------
st, d = post("/api/v1/risk", {"latitude": 12.9783, "longitude": 80.2209, "city": "mumbai"})
if st == 200:
    warn("city/coordinate mismatch accepted",
         "Chennai coords forced to city=mumbai returned %d/%s - scores a plot against "
         "another city's layers" % (d["composite_score"], d["composite_grade"]))
else:
    check("mismatch refused", st in (400, 422), "got %s" % st)

# ---------- 6. auto-detect city from coordinates ----------
for slug, (lat, lng) in CENTRES.items():
    st, d = post("/api/v1/risk", {"latitude": lat, "longitude": lng})
    check("%s auto-detected" % slug, st == 200 and d.get("city", {}).get("slug") == slug,
          "got %s / %s" % (st, d.get("city", {}).get("slug")))

# ---------- 7. caching consistency ----------
lat, lng = CENTRES["chennai"]
_, a = post("/api/v1/risk", {"latitude": lat, "longitude": lng, "city": "chennai"})
_, b = post("/api/v1/risk", {"latitude": lat, "longitude": lng, "city": "chennai"})
check("repeat call same score", a["composite_score"] == b["composite_score"],
      "%s vs %s" % (a["composite_score"], b["composite_score"]))
# same H3 cell, different city must not collide
_, c1 = post("/api/v1/risk", {"latitude": CENTRES["mumbai"][0], "longitude": CENTRES["mumbai"][1], "city": "mumbai"})
check("mumbai not serving chennai cache", c1["city"]["slug"] == "mumbai", c1["city"]["slug"])

# ---------- 8. geocoding ----------
for q, city in [("velacheri", "chennai"), ("koramangala", "bengaluru"),
                ("kukatpally", "hyderabad"), ("andheri", "mumbai"),
                ("saket", "delhi"), ("kothrud", "pune"),
                ("salt lake", "kolkata"), ("maninagar", "ahmedabad")]:
    st, d = get("/api/v1/geocode?q=%s&city=%s&limit=3" % (urllib.parse.quote(q), city))
    ok = st == 200 and len(d.get("results", [])) > 0
    check("geocode '%s' in %s" % (q, city), ok, "status %s, %d results" % (st, len(d.get("results", []))))
    if ok:
        r = d["results"][0]
        bbox = next(c["bbox"] for c in cities["cities"] if c["slug"] == city)
        inside = (bbox["lat_min"] - 0.3 <= r["latitude"] <= bbox["lat_max"] + 0.3
                  and bbox["lng_min"] - 0.3 <= r["longitude"] <= bbox["lng_max"] + 0.3)
        check("geocode '%s' lands in %s" % (q, city), inside,
              "got %.3f,%.3f" % (r["latitude"], r["longitude"]))
st, _ = get("/api/v1/geocode?q=a")
check("geocode rejects 1 char", st == 400, "got %s" % st)

# ---------- 9. layers ----------
for slug in slugs:
    st, d = get("/api/v1/layers?city=%s" % slug)
    check("%s layer list" % slug, st == 200, "got %s" % st)
st, d = get("/api/v1/layers/chennai/flood_zones")
check("chennai flood layer non-empty", st == 200 and len(d.get("features", [])) > 1000,
      "%d features" % len(d.get("features", [])))
st, d = get("/api/v1/layers/mumbai/flood_zones")
check("mumbai flood layer empty not 404", st == 200 and d.get("features") == [],
      "status %s" % st)
st, _ = get("/api/v1/layers/atlantis/wards")
check("unknown city layer 404", st == 404, "got %s" % st)

# ---------- 10. PDF ----------
for slug, (lat, lng) in CENTRES.items():
    st, body = get("/api/v1/report?latitude=%s&longitude=%s&city=%s" % (lat, lng, slug))
    ok = st == 200 and isinstance(body, (bytes, bytearray)) and body[:4] == b"%PDF"
    check("%s PDF" % slug, ok, "status %s" % st)

print()
print("PASS %d   FAIL %d   WARN %d" % (PASSES, len(FAILS), len(WARNS)))
if FAILS:
    print("\nFAILURES:")
    for f in FAILS:
        print("  x %s" % f)
if WARNS:
    print("\nWARNINGS:")
    for w in WARNS:
        print("  ! %s" % w)
