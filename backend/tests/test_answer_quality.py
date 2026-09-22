"""QA round 2: correctness of answers, not just HTTP status."""
import concurrent.futures, json, sys, urllib.error, urllib.parse, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
FAILS, WARNS, PASSES = [], [], 0

def check(name, cond, detail=""):
    global PASSES
    if cond: PASSES += 1
    else: FAILS.append("%s -- %s" % (name, detail))

def warn(n, d=""): WARNS.append("%s -- %s" % (n, d))

def post(path, payload, timeout=120):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try: return e.code, json.load(e)
        except Exception: return e.code, {}
    except Exception as e:
        return 0, {"err": str(e)}

def get(path, timeout=120):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            ct = r.headers.get("Content-Type", "")
            b = r.read()
            return r.status, (json.loads(b) if "json" in ct else b)
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"err": str(e)}

def score(slug, lat, lng):
    st, d = post("/api/v1/risk", {"latitude": lat, "longitude": lng, "city": slug})
    return d if st == 200 else None

print("=" * 78); print("QA round 2 -- answer correctness"); print("=" * 78)

# ---- 1. known-bad should outscore known-good within the same city ----
PAIRS = [
    ("chennai", (12.9060, 80.2050, "Perumbakkam"), (13.0850, 80.2101, "Anna Nagar"), "flood"),
    ("bengaluru", (12.9081, 77.6476, "HSR/Koramangala low"), (13.1007, 77.5963, "Yelahanka"), "scarcity"),
]
for slug, bad, good, dim in PAIRS:
    db, dg = score(slug, bad[0], bad[1]), score(slug, good[0], good[1])
    if db and dg and db.get(dim) and dg.get(dim):
        check("%s: %s %s >= %s" % (slug, bad[2], dim, good[2]),
              db[dim]["score"] >= dg[dim]["score"],
              "%d vs %d" % (db[dim]["score"], dg[dim]["score"]))

# ---- 2. severity floor and evidence ceiling actually fire ----
d = score("chennai", 13.1647, 80.2587)          # Manali: critically polluted cluster
check("severity floor fires in Manali", d and d["grade_floor_applied"], str(d and d["composite_grade"]))
d = score("mumbai", 19.0176, 72.8448)            # Dadar: baseline city, low score
check("evidence ceiling fires in Mumbai", d and d["evidence_ceiling_applied"],
      "grade %s raw %s" % (d and d["composite_grade"], d and d["unadjusted_grade"]))
check("ceiling never yields A in baseline city", d and d["composite_grade"] != "A",
      str(d and d["composite_grade"]))

# ---- 3. a deep-data city may still reach A ----
d = score("chennai", 13.0850, 80.2101)
if d:
    check("chennai A not blocked by ceiling", not d["evidence_ceiling_applied"],
          "ceiling applied in a surveyed city")

# ---- 4. composite equals the renormalised weighted sum ----
for slug, lat, lng in [("chennai",12.9783,80.2209), ("bengaluru",12.9352,77.6245),
                       ("mumbai",19.0726,72.8845), ("kolkata",22.5726,88.3639)]:
    d = score(slug, lat, lng)
    if not d: continue
    expect = round(sum(d["weights"][k] * d[k]["score"] for k in d["weights"]))
    check("%s composite matches weights" % slug, abs(d["composite_score"] - expect) <= 1,
          "got %d expected %d" % (d["composite_score"], expect))

# ---- 5. ward resolution accuracy against known ground truth ----
GROUND_TRUTH = [
    ("chennai", 12.9783, 80.2209, "177"), ("chennai", 13.0959, 80.2871, "60"),
    ("mumbai", 19.0176, 72.8448, "F/N"), ("mumbai", 19.0726, 72.8845, "L"),
    ("bengaluru", 12.9716, 77.5946, "Ashok Nagar"),
    ("hyderabad", 17.3850, 78.4867, "Abids"),
]
for slug, lat, lng, expect in GROUND_TRUTH:
    d = score(slug, lat, lng)
    got = (d or {}).get("administrative", {}).get("summary", "")
    check("%s ward @%.4f contains '%s'" % (slug, lat, expect), expect.lower() in got.lower(),
          "got '%s'" % got)

# ---- 6. bbox edge coordinates ----
st, cities = get("/api/v1/cities")
for c in cities["cities"]:
    b = c["bbox"]
    for name, lat, lng in [("SW", b["lat_min"] + 1e-4, b["lng_min"] + 1e-4),
                           ("NE", b["lat_max"] - 1e-4, b["lng_max"] - 1e-4)]:
        s2, _ = post("/api/v1/risk", {"latitude": lat, "longitude": lng, "city": c["slug"]})
        check("%s %s corner scores" % (c["slug"], name), s2 == 200, "status %s" % s2)

# ---- 7. odd inputs ----
st, _ = post("/api/v1/risk", {"latitude": 13.0827, "longitude": 80.2707, "address": "x" * 500})
check("over-long address rejected", st == 422, "got %s" % st)
st, d = get("/api/v1/geocode?q=" + urllib.parse.quote("!!!@@@###"))
check("junk query handled", st in (200, 400, 502), "got %s" % st)
st, d = get("/api/v1/geocode?q=" + urllib.parse.quote("velacheri' OR 1=1--"))
check("quote in query handled", st in (200, 400, 502), "got %s" % st)

# ---- 8. concurrency ----
def one(i):
    return post("/api/v1/risk", {"latitude": 12.9783 + i * 1e-4, "longitude": 80.2209,
                                 "city": "chennai"})[0]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    codes = list(ex.map(one, range(8)))
check("8 concurrent requests all 200", all(c == 200 for c in codes), str(codes))

# ---- 9. meta ----
st, m = get("/api/v1/meta")
check("meta 200", st == 200, str(st))
check("meta lists coverage for 8", len(m.get("coverage", {})) == 8, str(m.get("coverage")))

# ---- 10. PDF has three pages and names the city ----
for slug, lat, lng in [("chennai",12.9783,80.2209), ("mumbai",19.0176,72.8448)]:
    st, body = get("/api/v1/report?latitude=%s&longitude=%s&city=%s" % (lat, lng, slug))
    if st == 200 and isinstance(body, (bytes, bytearray)):
        check("%s PDF >=3 pages" % slug, body.count(b"/Type /Page") >= 3 or body.count(b"/Type/Page") >= 3,
              "page markers %d" % max(body.count(b"/Type /Page"), body.count(b"/Type/Page")))

print()
print("PASS %d   FAIL %d   WARN %d" % (PASSES, len(FAILS), len(WARNS)))
for f in FAILS: print("  x %s" % f)
for w in WARNS: print("  ! %s" % w)
