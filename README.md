# Property Risk Analyser

Parcel-level environmental risk screening for India's tier-1 cities. Drop a pin or search
an address and get three scores — monsoon flood, groundwater contamination, summer water
scarcity — a composite letter grade, and a three-page PDF due diligence report.

Indian property documents (patta, chitta, encumbrance certificates) verify ownership and
liens. They say nothing about whether the plot sits on a former lake bed, inside a
critically polluted industrial cluster, or in an overexploited groundwater block. This
fills that gap from open data.

**Live:** https://chennai-terra-risk.vercel.app

Worked examples with real output: [USE_CASES.md](USE_CASES.md). QA suites and the bugs
they caught: [backend/tests/](backend/tests/README.md). &nbsp;·&nbsp; API: https://chennai-terra-risk-api.vercel.app/docs

```
Composite = 0.45 x flood + 0.30 x contamination + 0.25 x scarcity

A  0-20   Resilient          D  61-80   High Risk
B  21-40  Low Risk           F  81-100  Critical Vulnerability
C  41-60  Moderate Risk
```

---

## Coverage, and why it is uneven

Eight cities are covered. They are **not** equally well served, and the tool says so on
every score rather than presenting a uniform-looking grade over wildly different
evidence.

| City | Depth | What actually backs the flood score | Groundwater |
|---|---|---|---|
| Chennai | **Full survey** | 7,453 graded GCC inundation polygons, validated against 53 recorded 2020 hotspots | Curated locality table (4 measured, 60 inferred) |
| Bengaluru | Partial | BBMP low-lying areas, 70 flood-prone points, 6,839 drain segments | **1,114 measured borewell depths** |
| Hyderabad | Partial | 23 GHMC flooding points | none |
| Mumbai | Terrain only | terrain, water, coast | none |
| Delhi | Terrain only | terrain, 2023 water census | none |
| Pune | Terrain only | terrain, rivers, 3,075 PMC nalla segments | none |
| Kolkata | Terrain only | terrain, 3,051 water census features | none |
| Ahmedabad | Terrain only | terrain, water | none |

Ward boundaries come from each corporation where they are published: 200 GCC wards,
225 BBMP wards, 155 GHMC wards, Mumbai's 24 lettered BMC wards, 141 KMC wards, 41 PMC
prabhags. **Delhi and Ahmedabad publish none.** For those two the tool shows the nearest
OpenStreetMap locality instead, labelled as such, and makes no boundary claim: OSM admin
levels there are villages and colonies that do not tile the city, so a containment test
would report "outside MCD limits" in the middle of Connaught Place.

Only Chennai publishes a graded flood survey. Nothing comparable exists for the other
seven, which is a fact about Indian open data, not an oversight here. Three mechanisms
keep that from quietly flattering the thinner cities:

**Unscoreable dimensions are dropped, not zeroed.** Six cities publish no groundwater
evidence, so water scarcity is not scored there at all and the remaining weights are
renormalised (flood 0.60, contamination 0.40). Scoring it zero would reward a city for
publishing less.

**The point budget shifts.** Chennai's inundation polygon carries up to 50 of the 100
flood points. Where no survey exists that budget moves onto terrain, recorded flooding
and water proximity — otherwise the ceiling for a genuinely dangerous Mumbai plot would
be about 60, and every under-surveyed city would look safer than it is.

**An evidence ceiling caps the grade at B.** This is the mirror of the severity floor.
"A — Resilient" is a positive claim, and in a city with no graded flood survey and no
groundwater data it is a claim about what nobody has measured. A Mumbai plot scoring 16
is held at B, and the report says the cap is about the data, not the plot.

---

## Quick start

Two processes: a FastAPI backend on `:8000` and a Next.js frontend on `:3000`.

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-data.txt
```

```bash
cd backend && make data
```

That downloads and prepares everything (~70 MB, a few minutes; it caches, so re-runs are
cheap). Then in two terminals:

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. The frontend proxies `/api/*` to the backend, so there is no
CORS setup and no API keys anywhere in the stack.

Score a point without the UI:

```bash
curl -X POST http://localhost:8000/api/v1/risk -H "Content-Type: application/json" -d '{"latitude":12.9783,"longitude":80.2209}'
```

---

## Does it actually work?

The flood model is the one dimension with independent ground truth, so it is the one
that can be honestly tested. The 53 GCC-recorded 2020 (Cyclone Nivar) flood hotspots are
**not** derived from the inundation polygons the score is built from.

Two checks, both in `scripts/validate_flood_layer.py` and `scripts/validate_scoring.py`:

**1. Is the source layer's `CATEGORY` field meaningful?** Recorded hotspots concentrate
in the high categories far above those categories' share of the city's area, and the lift
falls monotonically down the scale:

| CATEGORY | share of city area | recorded hotspots | lift |
|---|---|---|---|
| Very High | 6.1% | 35.3% | **5.81x** |
| High | 4.8% | 9.8% | 2.06x |
| Moderate | 5.1% | 5.9% | 1.16x |
| Low | 36.7% | 29.4% | 0.80x |
| Very Low | 47.4% | 19.6% | 0.41x |

High + Very High together are 10.8% of the city's area and contain 45% of recorded
hotspots.

**2. Does the composite flood score separate real flooding from ordinary parcels?**
Hotspots vs. 300 parcels drawn at random from inside the same surveyed footprint,
area-weighted:

| | n | mean | median |
|---|---|---|---|
| 2020 recorded hotspots | 53 | **48.6** | 41.0 |
| random GCC parcels | 300 | 34.3 | 30.0 |

A separation of +14.3 points, and a parcel that actually flooded is **2.2x** more likely
to score 50 or above.

Contamination separates by +43.8 points between known industrial/waste zones and control
localities. Scarcity has no independent ground truth available and is the weakest of the
three — it is reported with explicit confidence levels rather than false precision.

Latency: uncached score **~3 ms**, PDF **~0.2 s** (targets were 3 s and 5 s).

### What the numbers do not tell you

Per-locality spot checks at centroids look unimpressive, and that is expected: a centroid
says nothing about the parcel next door. Velachery's centroid scores 31 while a point a
few hundred metres away scores 70+. Scoring points rather than neighbourhoods is the
entire purpose of the tool, so neighbourhood-level tests are the wrong instrument.

---

## Search, and the ward/zone answer

Buyers search in the language they speak. They type "velacheri", "anna nagar 2nd avenue",
"near phoenix mall", "OMR", "porur signal". Nobody types a ward number. But a ward number
is exactly what patta records, GCC building approvals and CMWSSB connections are filed
against, so the tool takes the everyday phrasing in and hands the official nomenclature
back out.

Every result reports the **ward** the point falls in, resolved against that city's own
published boundaries — 200 GCC wards in Chennai, 225 BBMP wards in Bengaluru, 155 GHMC
wards, Mumbai's 24 lettered BMC wards, 141 KMC wards, 41 PMC prabhags:

```
velacheri bus stop  ->  Velachery, Chennai 600042  ->  Ward 177, Zone 13 Adyar
```

The map outlines that ward so you can see how far it extends. Outside corporation
limits, the tool says so and names the nearest zone rather than guessing a ward that
does not exist: *"Outside GCC limits, 578m from Zone 14 Perungudi"*, plus a note that a
panchayat governs approvals, tax and water there. Cross-check: Nominatim independently
labels the Mannady test point "Ward 60, Zone 5 Royapuram", which is what the resolver
returns.

Getting there took three fixes.

**Photon, not Nominatim, as the primary geocoder.** Photon is built for type-ahead: it
tolerates misspellings and matches partial street names and landmarks. Nominatim returns
*nothing* for "velacheri" or "medavakam"; Photon returns Velachery and Medavakkam. Photon
also has no one-request-per-second limit, so results arrive as you type (220 ms debounce)
instead of a second later. Nominatim remains as a fallback.

Local shorthand is expanded before searching (`OMR` → Old Mahabalipuram Road, `ECR` →
East Coast Road, `GST` → Grand Southern Trunk Road, `Mount Road` → Anna Salai), and filler
words are stripped, so "near phoenix mall" and "plot in t nagar" both work. When a query
is rewritten the UI says so, rather than silently searching for something else.

**Relevance re-ranked on the distinctive word.** Photon ranked "Perambur Loco Works
Railway Station" first for "thiruvanmiyur railway station", because the generic words
matched perfectly and the one word that mattered did not. Results are re-scored so
distinctive tokens outweigh the filler ones, and query intent ("station", "signal",
"bus stop") boosts matching categories. For "<type> in <area>" queries that still come
back weak, the area is resolved first and the search re-run around it, with results more
than 3 km from that area dropped. Where OSM has no such landmark, the area itself is
offered instead: dropping you on Velachery beats dropping you on a bus stop 4 km away in
Adyar. This also rescues queries Photon fails outright, like "porur signal", which
returns a street in Ohio and a firm in New Zealand.

**No government vocabulary in the results.** Nominatim hands back labels like
`Mannady, Ward 60, Zone 5 Royapuram, Chennai Corporation, Chennai, Tamil Nadu, 600079,
India`, and even Photon's own `locality` field carries entries like `CMWSSB Division 178`.
Both are filtered out. A result is shown as a name, a plain-language location, and a
category badge:

```
100 Feet Road                                    [Street]
Velachery, Chennai 600042
```

The same cleaned label is what appears on the scorecard and as the PDF report heading.
Results are deduplicated, restricted to the Chennai region, and navigable by keyboard
(arrows, Enter, Escape).

---

## Interface

Map first. The map fills the window and the panels float over it, so nothing competes
with the thing you are reading.

**One question at a time.** Seven independent layer checkboxes let anyone build an
unreadable screen, and the default was already close to one: hazard, water, drains,
industry, hotspots, dumpyards and ward lines stacked over a city-wide choropleth. That is
now a single four-way choice — Flood, Water, Industry, None — mapped onto the three risks
the tool scores, so picking a view is picking a question. It is a Radix ToggleGroup rather
than a hand-rolled row of buttons, which brings arrow-key navigation and correct radio
semantics the checkbox panel never had. Ward boundaries are one separate checkbox, off by
default. The whole control collapses behind a single "Map" button.

**Readable by someone who is not twenty-five.** The palette was measured against WCAG,
not eyeballed, and it failed in the places that mattered most: the muted ink used on every
small label sat at 3.50:1, the amber score number at 1.79:1, and white on the amber grade
chip at **1.83:1** — effectively unreadable. Text tones are now darkened until they clear
4.5:1; bright hues survive only as fills and marks, with dark ink on top. Body text went
from 13px to 15–16px, section labels from 10px to 12px, and every control has a 44px
minimum target. Numbers stay in ink with a coloured dot beside them, so colour reinforces
the reading instead of carrying it. Weights read as "Counts for 45% of the total" rather
than "Weight 0.45".

**The basemap is deliberately drab.** Positron renders roads and labels in grey, which
leaves the hazard ramp as the only saturated thing on screen. A colourful basemap and a
colourful data layer fight, and the data loses.

**The flood scale is one hue, not a rainbow.** Five ordered hazard levels are ordinal
data, so the ramp runs light to dark in a single hue. The red-amber-green scale this
started with encoded the order in hue rather than in value, which collapses under
colour-vision deficiency and reads as five unrelated categories. The replacement ramp was
checked with the data-viz skill's validator, not by eye: monotone lightness, adjacent
step gaps, light end at 2.21:1 against the surface, 6° hue spread. Grades use the
reserved status scale and always ship with the letter and the band name, so colour never
carries the meaning alone.

**One hero number per view.** The composite score is the only large figure; everything
else is small. Meter tracks are a lighter step of the fill's own hue so state reads
across the whole bar rather than only the filled part.

Copy went through the anti-slop pass. Warnings name an actor and tell you what to do:
"GCC records the nearest storm water drain as in bad condition" and "Test any borewell
here for heavy metals in a laboratory before you drink, cook or bathe with it", rather
than the passive hedging they started as.

---

## Design decisions worth knowing

**No PostGIS.** The brief allows starting simpler for the MVP. The whole corpus is ~22k
features, which loads into a shapely STRtree in 1.5 s and answers queries in
microseconds. Everything is reprojected once to UTM 44N at load, so every distance is
true metres with no per-request trigonometry. A disk cache makes warm starts ~0.2 s.
`app/core/geo.py` is the seam to swap in PostGIS when write concurrency demands it.

**A parcel is not a point.** The GCC inundation layer tiles the city but leaves small
gaps along roads, so strict point-in-polygon returns false negatives — Velachery's own
centroid falls in a gap 38 m from the nearest polygon. The engine reads a 40 m window
first, then falls back to 150 m at a 0.6 discount and downgrades confidence.

**Relative elevation, not absolute.** A plot two metres below its neighbours collects
their runoff whatever its height above sea level. Each lookup requests a 9-point stencil
(the parcel plus a 250 m ring) in one batched call and scores the difference. Velachery
reads 5 m absolute but **-2.5 m relative** — that second number is the one that matters.

**Drain condition, not just drain distance.** The GCC storm water dataset carries
`STATUS` per segment; 824 of 10,255 segments are recorded as "Bad". A parcel next to a
failing drain is scored worse than one next to a working drain, and the map draws bad
drains in red.

**Absence of data is not absence of risk.** The drain network only covers GCC zones
N01–N15. Outside it, "no drain within 500 m" means the area was never surveyed, so the
engine says so and downgrades confidence instead of inventing a penalty. Same for parcels
outside the flood survey.

**A severe single risk is not averaged away.** A weighted mean lets one critical
dimension be diluted by two mild ones: a parcel inside a CPCB critically polluted cluster
scoring 62 on contamination came out **"Grade B — Low Risk"**. Good drainage does not make
contaminated groundwater safe to drink. Where any dimension scores >=61 the headline grade
is capped at C, and >=81 at D. The composite score is left exactly as the brief specifies
and the unadjusted grade is always reported alongside.

**Provenance is tracked per record.** Curated data distinguishes `cpcb_cepi` (a published
numeric index) from `locality_flag` (named as high-risk, no published number), and
`cgwb_cited` from `cgwb_regional` (inferred from CGWB's finding that 46 of 51 Chennai
blocks are overexploited). The API reports which applied, and confidence drops when a
score leans on the weaker kind.

---

## Deviations from the brief

| Brief | Built | Why |
|---|---|---|
| PostGIS + Docker | In-memory STRtree | No Docker in the target environment; 22k features do not need a spatial database. Swappable at `app/core/geo.py`. |
| WeasyPrint | ReportLab | WeasyPrint needs cairo/pango system libraries that were not installable. ReportLab turned out better here: the locality map is drawn as true offline vectors rather than a fetched raster. |
| `elevation` + `richdem` (SRTM GeoTIFF) | Open Topo Data API | `elevation` shells out to GDAL, unavailable without system packages. Open Topo Data serves the same SRTM 30 m product over HTTP, and the brief lists it as the point-query option. |
| MapLibre demo tiles | OpenFreeMap | The demo style has no street detail, which makes picking an actual parcel impossible. Both are free and keyless. |
| Flood zones HIGH/MODERATE/LOW | 5 categories | The real GCC data has Very Low → Very High. Validated as monotonically predictive. |

---

## Multi-city architecture

Three things had to stop being Chennai-shaped:

**Projection.** Every distance in this app is measured in a metric CRS, and India spans
three UTM zones. Ahmedabad, Mumbai, Pune, Delhi and Bengaluru sit in 43N, Chennai and
Hyderabad in 44N, Kolkata in 45N. Each city carries its own EPSG and measures in it;
running Kolkata against Chennai's zone would skew every distance the score depends on.

**Loading.** Stores are per city and load lazily, so a Mumbai request never pays for
Chennai's 25 MB of inundation polygons. Cold start stays proportional to one city
rather than eight.

**Ward readers.** No two corporations publish the same shape. Chennai numbers wards
1-200 inside named zones; Mumbai uses letter codes (G/S, F/N); Bengaluru names its
wards; Hyderabad packs ward, circle and zone into one field; Pune publishes a prabhag
number as a bare float with no name; Delhi and Ahmedabad publish nothing at all, so
their wards come from OpenStreetMap admin boundaries. Each city gets its own reader
rather than a lowest-common-denominator guess.

---

## Deployment

Two Vercel projects, deployed from their own directories:

```bash
cd backend && npx vercel deploy --prod      # API
```

```bash
cd frontend && npx vercel deploy --prod     # UI
```

The frontend proxies `/api/*` to the API via `next.config.ts`, so the browser only ever
talks to one origin and there is no CORS configuration. The target comes from the
`API_ORIGIN` build-time environment variable, already set on the Vercel project. If you
redeploy the API to a different URL, update that variable and rebuild the frontend.

Three things make the Python API work in a serverless function:

- **`data/spatial_cache.pkl` ships; the source GeoJSON does not.** `.vercelignore` keeps
  the 40 MB of raw and processed GeoJSON out of the bundle. The function loads the
  prebuilt 25 MB cache instead and is serving in ~1.3 s cold, ~5 ms warm. Rebuild the
  cache with `make data` before deploying if the sources changed.
- **Cache staleness is judged by content hash, not mtime.** Uploading rewrites every
  mtime, which made a perfectly good cache look stale and left the API answering with
  empty layers — a 200 response with every score wrong. Hashes survive the trip, and a
  source that is absent entirely is treated as "cannot tell", so the cache is trusted
  rather than discarded.
- **`requirements.txt` is kept lean.** It had accumulated the WeasyPrint dependency chain
  from an abandoned experiment — ~30 MB of a 250 MB function budget for code nothing
  imports. Data-pipeline-only packages live in `requirements-data.txt`.

`GET /api/v1/health` reports per-layer feature counts and whether the cache was found, so
a deploy that shipped without its data is obvious rather than silently wrong.

**Worth knowing:** a serverless function is not an ideal host for a 25 MB in-memory
spatial index — every cold start pays ~1.3 s to rebuild it. It is fine at this traffic
level, and warm requests are ~5 ms. If this ever gets steady use, a small always-warm
container (Render, Fly, Railway) suits the workload better; `app/core/geo.py` is the only
file that would need to change.

## Layout

```
backend/
  api/index.py    Vercel serverless entry point
  app/
    api/          risk, geocode, layers, report endpoints
    core/         geo (spatial store), config (all thresholds), scoring, elevation,
                  places (query expansion, ranking, jargon-free labels)
    engines/      flood, contamination, scarcity, administrative (ward/zone)
    pdf/          ReportLab report with a vector locality map
  scripts/
    ingest_kml.py           download + convert the three GCC KMLs
    fetch_osm.py            Overpass: water, industrial, coastline, landfill
    build_manual.py         curated CPCB / CGWB datasets with provenance
    build_map_layers.py     simplify GeoJSON for the browser (33 MB -> 4.25 MB)
    validate_flood_layer.py is CATEGORY meaningful?
    validate_scoring.py     end-to-end scoring, latency and degradation checks
frontend/
  src/components/  MapView (MapLibre), SearchBar, ScoreCard, LayerToggle
  src/lib/api.ts   typed API client
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/risk` | Score a parcel. Also available as GET for quick curl checks. |
| `POST /api/v1/report` | Three-page PDF. |
| `GET /api/v1/geocode?q=` | Nominatim search, proxied and throttled server-side. |
| `GET /api/v1/layers/{name}` | Simplified GeoJSON for the map (gzipped). |
| `GET /api/v1/meta` | Weights, grade bands, data provenance. |
| `GET /api/v1/health` | Loaded layer counts. |

Interactive docs at http://localhost:8000/docs.

## Data sources

All open-licensed. GCC flood inundation zones, storm water drain network and 2020 flood
hotspots via [OpenCity.in](https://data.opencity.in/dataset/chennai-flooding-data);
elevation from NASA SRTM 30 m via [Open Topo Data](https://api.opentopodata.org);
waterbodies, industrial land use and coastline from OpenStreetMap (ODbL) via Overpass;
CPCB CEPI industrial pollution scores and CGWB/CMWSSB groundwater status curated from
published reports.

## Limitations

- Groundwater "firkas" are locality centroids with an influence radius, not real
  administrative polygons — CGWB does not publish downloadable boundaries.
- Piped-supply reach uses the GCC boundary as a proxy; CMWSSB publishes no
  machine-readable supply zones.
- Only three industrial clusters carry published CEPI numbers. The rest are flagged
  localities with no numeric index, and are marked as such.
- Flood and drain coverage stops at the GCC boundary. Outside it the tool says so.

> This is a screening tool. It does not constitute a professional environmental
> assessment. Verify all findings with a physical site visit and consult a qualified
> surveyor before making purchase decisions.
