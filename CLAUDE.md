# TerrisIQ — Architectural Manifest & Working Contract

TerrisIQ (www.terrisiq.com) + the Chrome extension: property-risk intelligence. This file is the
persistent north star. It encodes the **vision**, the **non-negotiable guardrails**, and the
**two-phase architecture** that keeps us honest about what runs where. Read it before large changes.

Derived from the "Cadastral-to-Orbital" blueprint (see `BLUEPRINT_ANALYSIS.md` for the reality check)
and adapted to what this repo and its hosting can actually run.

---

## 1. MISSION & NORTH STAR

Evolve TerrisIQ from a static hazard-screening app into a **Cadastral-to-Orbital property & climate risk
platform**: fuse **parcel-level statutory/legal verification** with **all-weather orbital physics** and
an **honest, citation-bound AI**, serving retail buyers through institutional underwriters (RBI climate
directions, SEBI BRSR), across India and the US/global market.

The moat is **physical measurements clipped to legally-defined parcels, every number cited to its source**.

Preserve what already works: the frictionless point-of-decision UX, fast onboarding, and the
"screening only, verify before you buy" honesty. Never trade that away for scope.

---

## 2. GUARDRAILS (NON-NEGOTIABLE)

1. **No scraping of restricted government portals.** Never write scrapers that defeat CAPTCHAs, session
   tokens, or rate limits on transactional portals (TNREGINET, Tamil Nilam, Bhu-Naksha, etc.). This is
   IT Act 2000 §43/§66 + Copyright Act 1957 territory, and it is what got the extension pulled from the
   Web Store. Cadastral/title data comes ONLY from: official federated gateways (API Setu, DigiLocker,
   DoLR ULPIN) under proper onboarding; open spatial portals (TNGIS, data.opencity.in, Survey of India);
   **user-consented document uploads**; or AI delineation from licensed imagery (SamGeo, Overture, MS/Google
   building footprints).
2. **Licensing is confirmed before building on a dataset.** We already established: **TN parcel/ULPIN is
   NOT openly licensed**, and the **official CZMP/CRZ GIS is NOT open**. Absence of a license is not
   permission. A parcel layer waits for a licensed source or authorized API access — it is never scraped.
3. **GPL-3.0 clean-room isolation.** MintPy, PyAPS, PySolid (GPL-3.0) never import/link/bundle into our
   proprietary services. They run only in an isolated worker (Phase B) that talks via a job queue + object
   storage. Core services stay on permissive licenses (Apache-2.0 / MIT / BSD).
4. **Provenance on every number.** Every quantitative metric and AI answer exposes its physical units
   (m/yr, dB, m AMSL, m AGL, FSI, % recurrence) and cites its source — dataset, satellite granule ID +
   timestamp + polarization, or the exact statute/rule number. The AI answers ONLY from computed data and
   admits what it does not know. Honesty about the data is the product.
5. **Privacy on consented uploads.** User documents (Patta/EC/FMB) contain personal data. Uploads are
   explicit opt-in, used only to serve that user's report, and the external-service path (e.g. an LLM
   vision parser) is disclosed. Never log or expose document contents.
6. **No secrets in the client or the repo.** Keys live in server env only (see `GEMINI_API_KEY` pattern
   in `backend/app/api/chat.py`).

---

## 3. CURRENT BASELINE (what exists today)

- **Backend:** FastAPI on **Vercel serverless** — hard **250 MB** bundle budget, 30 s max duration.
  Lean deps: `fastapi, pydantic, shapely, pyproj, numpy, h3, httpx, reportlab`. No Docker, no GDAL, no
  torch. Entry: `backend/api/index.py` → `app.main:app`. Routers under `backend/app/api/`,
  spatial logic in `backend/app/engines/`, scoring in `backend/app/core/`.
- **Frontend:** Next.js 16 + MapLibre GL on Vercel. Components in `frontend/src/components/`.
- **Local box:** Python 3.9 only, no Docker/brew/GDAL. Treat anything needing those as Phase B.
- **Shipped risk engines:** flood, contamination, scarcity, composite; `crz.py` (CRZ screening from the
  open OSM coastline — a proxy, labelled "verify against the CZMP"); `nowcast.py` (live rain × flood +
  official NDMA/IMD alerts); `us_flood.py` (FEMA NFHL flood + EPA ECHO contamination); `universal.py`
  (terrain+OSM BASELINE so any India point is scoreable); `india_hazards.py` (bundled CPCB CEPI / CGWB /
  AAI national index → MODERATE). **Coverage is nationwide** — all of India and all 50 US states — via
  one resolver (`assess_point`); every point returns a cited read at a DEEP / MODERATE / BASELINE
  confidence tier (see `COVERAGE.md`). Chennai is the only validated flood survey.

---

## 4. TWO-PHASE ARCHITECTURE

The blueprint is a Docker/GPU/stateful platform. Our hosting is serverless. So we split it explicitly and
never pretend Phase B work can run in Phase A.

### Phase A — Vercel-Native Serverless Stack (zero-Docker, ≤250 MB, pure-Python/TS)
Everything buildable now with no new infra, credentials, or licensing risk. **Default target for all work
unless a task is explicitly Phase B.**
- **Build Scope (TNCDBR) calculator** — deterministic FSI / setbacks / coverage / OSR / parking / AAI net
  height (AGL = PTE − G) math + NOC checklist + pure-text `.dxf` / `.geojson` export. No spatial data, no
  GDAL.
- **Evidence & Underwriting drawer** — re-expose existing flood/scarcity/contamination/CRZ/nowcast outputs
  with units + source citations, sensor-to-ground-truth calibration notes.
- **Survey-no / ULPIN lookup field** — accept + parse + validate the 14-char ULPIN; return an honest
  "parcel source pending authorized access" state. Ships the rail; wires to API Setu later.
- **Consented document upload UX + serverless parse** — drag-drop + consent; parse via `pypdf` text +
  an LLM vision API for Tamil/English Patta/EC fields. OCR of scanned images beyond that is Phase B.
- **HTTP-only STAC + GeoIntent adapter** — query public NASA CMR / Earth Search STAC over plain HTTPS
  (no GDAL/rasterio) to show real granule IDs + timestamps; typed `GeoIntent` JSON for deterministic
  map-agent control (viewport/layers/time/selection), no screenshot/DOM driving.

### Phase B — External GPU / PostGIS Cloud (separate services, NOT Vercel, NOT this laptop)
Needs managed Postgres (PostGIS/pgSTAC/pgvector), object storage (S3/R2), a queue, and GPU. Gated on
accounts + spend + data licensing. Design before build.
- Raster/tile serving (pgSTAC + TiTiler), full 33-point PostGIS statutory engine (needs digitized city
  GIS layers), NISAR/OPERA ingestion (Earthdata/Bhoonidhi creds + GDAL), InSAR subsidence (isolated
  MintPy GPL worker + GPU), GeoFMs (Prithvi/Clay/Satlas/SamGeo), heavy Document AI (LayoutLMv3/Donut).
- Candidate hosts: Supabase/Neon (Postgres), Modal/RunPod (GPU), Cloudflare R2 / S3 (object store).

**Off-keyboard prerequisites for Phase B** (user's calls, not code): NASA Earthdata + ISRO Bhoonidhi
accounts; API Setu / DoLR authorized-consumer onboarding; the backend host + GPU spend (≥4 figures/mo);
Razorpay live + a WhatsApp BSP for the commercial tiers.

---

## 5. COMMERCIAL DIRECTION (reference, build incrementally)

4 tiers × 8 personas from the blueprint: Tier 1 retail Verified Plot Report (₹499–₹999); Tier 2 NRI
All-Weather Property Watch (₹4,999/yr, WhatsApp); Tier 3 Pro GIS + Build Scope + legal evidentiary
(₹14,999–₹29,999/mo); Tier 4 enterprise underwriting API + RBI portfolio monitor + SEBI BRSR + US/global
(₹2.5L–₹10L+/yr). Build the value before the paywall; don't gate what isn't proven.

---

## 6. CONVENTIONS

- Match surrounding code: clear module docstrings that explain the **why**, honest about data limits,
  lean deps (every MB counts against the 250 MB budget — justify any new dependency).
- New engine → `backend/app/engines/`; new route → `backend/app/api/` + register in `app/main.py`;
  extend `RiskResponse` in `app/models/schemas.py` and the `RiskResult` interface in
  `frontend/src/lib/api.ts` together.
- Never recolor the WCAG-measured hazard ramp or the map UI; brand orange is card chrome only.
- Tests in `backend/tests/` with `pytest`; verify engine math before wiring UI.

---

## 7. EXECUTION ORDER (current slice)

1. Build Scope (TNCDBR) calculator — engine + schema + route + tests.
2. STAC + GeoIntent adapter (HTTP-only).
3. Consented upload UX + serverless parse.
4. Evidence & Underwriting drawer + ULPIN/survey field (frontend).

Each step: build on the current stack, verify, keep the public site unaffected.
