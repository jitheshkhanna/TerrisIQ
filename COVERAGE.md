# TerrisIQ — Coverage & Confidence

What TerrisIQ can score, where, and **how much to trust each number**. The product is
nationwide for India and the US: *every* point returns a cited, honest read — but the
confidence tier tells you whether that read stands on a surveyed polygon, a national atlas,
or terrain physics alone. Thin data is always **labelled**, never dressed up as "safe".

Every point routes through one resolver (`assess_point`): **US → FEMA/EPA**, **inside a
surveyed Indian city → that city's engine**, **anywhere else in India → the universal
baseline**, **outside both → an honest 422** naming the nearest covered city.

## Confidence tiers

| Tier | What it means | Sources |
|------|---------------|---------|
| **DEEP** | A surveyed statutory/federal polygon under the point. | Chennai GCC flood survey (7,453 polygons); US FEMA National Flood Hazard Layer |
| **MODERATE** | A point match against a cited national/regional dataset. | CPCB CEPI polluted clusters; CGWB regional groundwater; EPA ECHO facilities; AAI airport funnels |
| **BASELINE** | Terrain physics + live OpenStreetMap hydrology. Works anywhere; a screening signal, not a survey. | Global SRTM elevation (catchment-relative); OSM Overpass water/drain/coastline |

A single report can mix tiers — e.g. a rural Tamil Nadu plot reads flood at BASELINE
(terrain) while its scarcity comes from CGWB at MODERATE.

## India

- **Surveyed cities (8):** Chennai, Mumbai, Delhi, Bengaluru, Hyderabad, Kolkata, Pune,
  Ahmedabad. **Chennai is the only validated flood survey (DEEP);** the others carry
  city-registry layers and otherwise fall through to the baseline, so they never over-claim.
- **Everywhere else in India:** the **universal baseline** scores every point from terrain +
  OSM, lifted to **MODERATE** wherever the bundled national index matches:
  - **Contamination** — CPCB CEPI industrial clusters (Manali, SIPCOT Ranipet/Cuddalore,
    Vapi, Ankleshwar, Patancheru, Ludhiana, Kanpur, …).
  - **Scarcity** — CGWB "Dynamic Ground Water Resources" state category (overexploited →
    safe).
  - **Airport NOC** — AAI/defence aerodrome obstacle funnels feed the Build Scope height
    clearance.
- **Build Scope** adapts by jurisdiction: **Tamil Nadu** uses the bundled TNCDBR-2019
  indicative table; the **rest of India** uses an NBC-2016 baseline and asks for the plot's
  local DCR FSI rather than inventing one.

## United States (all 50 states + DC)

- **Flood** — FEMA NFHL per-point (DEEP). When FEMA has no mapping for a point (unmapped
  county, or the service is unreachable), the flood score **falls back to the terrain
  baseline** and says so — it is **never** returned as grade A "very low risk".
- **Contamination** — EPA ECHO regulated-facility proximity (MODERATE; a proximity screen,
  not a plume model).
- **Scarcity** — not yet scored for the US; the dimension is dropped-and-labelled, and the
  composite is held at "low risk" not "very low" so the gap is explicit.
- **Build Scope** — FAR terminology, FAA (14 CFR Part 77) height authority, local municipal
  zoning as the authority; FAR comes from the user's zone.

## Out of scope

Points outside India and the US return a 422 that names the nearest covered city, rather
than a fabricated score.

## Guardrails behind every number

- **No scraping** of restricted government portals — only open federal/national APIs,
  permissively-licensed bundled indices, and user-consented uploads.
- **Provenance + physical units** on every metric; the source (dataset / statute / granule)
  is always named.
- **A dropped source never destroys a read and never reads as zero hazard** — every network
  call is fail-soft with a short timeout and a terrain fallback.
- **FSI/FAR is never invented** outside Tamil Nadu — it is genuinely local, so the engine
  asks for it instead of guessing.

_Regenerate the confidence a point actually received from the `city.depth` /
`confidence` / each dimension's `basis` fields in the `/risk` response._
