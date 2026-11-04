# TerrisIQ "Cadastral-to-Orbital" Blueprint — Analysis & Reality Check

_Analysis of `TerrisIQ Claude Code Master Prompt.pdf` (35 pages) against the actual repo and this project's hard constraints. Written 2026-11-03._

## 1. What the document is

A 35-page strategy report + a drop-in `CLAUDE.md` "master prompt" that wants to turn TerrisIQ from a
static hazard-screening app into an **institutional "Cadastral-to-Orbital Risk Intelligence Engine"**:

- **Cadastral/legal layer** — 33-point statutory land diligence (CMDA/DTCP/BDA/HMDA zoning, CRZ, AAI
  height, NGT/ASI buffers), a TNCDBR "Build Scope" FSI/Rule-47 calculator, consented Patta/EC/FMB
  document AI (LayoutLMv3/Donut), ULPIN/API Setu ingestion, SamGeo parcel delineation.
- **Orbital physics layer** — NISAR L/S-band SAR flood recurrence, OPERA DSWx/DIST/DISP, InSAR mm-scale
  subsidence via MintPy (GPL, isolated), Prithvi-EO-2.0 + Clay v1.5 + SatlasPretrain GeoFMs, live IMD
  radar + CartoDEM TWI nowcast.
- **Agentic layer** — NASA-IMPACT akd-suite/akd-care LangGraph agents, GeoUI-Intent map control, modern-dgf
  governance for RBI/SEBI audit trails.
- **Commercial layer** — 4 pricing tiers (₹499 retail → ₹10L+/yr enterprise API) × 8 personas; US/global.
- **Infra** — Docker monorepo: PostGIS + pgSTAC + pgvector + TiTiler + Redis/Celery + an air-gapped MintPy
  GPL worker; 90-day / 3-sprint roadmap.

**The guardrails in the doc are good and match what we already enforce:** no scraping of TNREGINET/Tamil
Nilam (IT Act §43/66), GPL clean-room isolation, Bhoonidhi rate-limit protection, and
unit/granule-cited provenance for every number. Nothing in it asks us to break the rules we set.

## 2. Verdict

**This is a well-researched Series-A deep-tech company roadmap, not a task this machine or the current
deployment can execute as written.** It's directionally excellent and worth mining — but ~80% of it is
gated on infrastructure, cloud accounts, data licensing, and headcount we don't have. Executing "Steps
1–7" literally would rip up a working product into a monorepo that cannot run here or on Vercel.

## 3. The four hard gaps (why we can't just run it)

### A. Infrastructure — the whole thing is Docker/GPU/stateful; we are Vercel serverless
- Local box: **Python 3.9 only, no Docker, no brew, no GDAL** (established constraint).
- Repo today: lean **FastAPI on Vercel** (hard 250 MB bundle budget) + **Next.js 16** on Vercel. Deps are
  `fastapi, shapely, pyproj, numpy, h3, httpx, reportlab` — no PostGIS, no torch, no GDAL.
- The blueprint needs long-running PostGIS+pgSTAC+pgvector, Redis/Celery workers, GPU GeoFM inference, and
  an air-gapped InSAR container. **None of that is a Vercel function or a laptop job** — it's a managed
  Postgres + a GPU cloud + an object store + a queue. Different hosting model entirely.

### B. Data access — every orbital/cadastral source is behind a credential or an onboarding we don't have
- **NISAR** L/S-band data → NASA Earthdata login + ASF; mission is new, latency/coverage still ramping.
- **ISRO Bhoonidhi** → account + the 20-token/hr, 5-concurrent-download limits the doc itself flags.
- **API Setu / DoLR ULPIN** → *authorized B2B consumer* onboarding (NDSAP/NeGD). Not self-serve; this is
  a business/legal process, not a code task.
- **CMDA/DTCP/BDA/HMDA/CRZ/AAI layers** → must be sourced and digitized into PostGIS. That's a large,
  ongoing GIS data-engineering effort per city, not something code conjures.

### C. Licensing — already confirmed open for parcel data is **not** there
- We established earlier: **TN parcel/ULPIN is not openly licensed** (TNREGINET is per-lookup only), and
  the **official CZMP/CRZ GIS is not open** (MoEFCC all-rights-reserved). The blueprint's lawful path for
  parcels is API Setu + *user-consented uploads* — correct, but that depends on (B)'s onboarding plus a
  consent/upload product we haven't built. **No shortcut exists that doesn't involve scraping, which stays
  off the table.**

### D. Scope — 90 days, multiple specialists
InSAR geodesy, GeoFM fine-tuning, cadastral law, GIS digitization, payments, WhatsApp BSP, and RBI/SEBI
compliance are each their own workstream. This is a team quarter, not a prompt.

## 4. Blueprint → reality map

| Blueprint module | Buildable on current stack now? | Blocker |
|---|---|---|
| CRZ screening (coastline proxy) | ✅ **Done** (`crz.py`, OSM coastline) | — |
| Live rain×flood nowcast + official alerts | ✅ **Done** (`nowcast.py`, Open-Meteo + NDMA) | — |
| US flood (FEMA NFHL) | ✅ **Done** (`us_flood.py`) | — |
| Evidence drawer / unit-cited UI | 🟡 Partly feasible now (pure frontend) | just build time |
| Survey-no / ULPIN **lookup field** (UX shell) | 🟡 UI feasible; returns "needs source" | data = API Setu onboarding |
| Consented Patta/EC/FMB **upload UX** | 🟡 Upload + storage feasible | OCR/NER models need GPU host, not Vercel |
| 33-point statutory engine | 🔴 Needs digitized city GIS layers + PostGIS | data + infra |
| Build Scope TNCDBR / Rule-47 DXF | 🟡 Rule math feasible as a module | needs per-city rule tables; no spatial dep |
| Sentinel-1 SAR flood recurrence | 🟡 Feasible via open archives | needs a raster backend, not Vercel |
| NISAR / OPERA ingestion | 🔴 Needs Earthdata/Bhoonidhi + GDAL + object store | credentials + infra |
| InSAR subsidence (MintPy) | 🔴 GPL Docker worker + GPU + SAR stacks | infra + data |
| GeoFMs (Prithvi/Clay/Satlas/SamGeo) | 🔴 torch + GPU + GDAL | infra |
| akd-suite agentic + GeoUI protocol | 🟡 Agent/protocol layer portable; tools gated | depends on the engines above |
| pgSTAC + TiTiler tile serving | 🔴 Stateful services | infra |
| 4-tier billing (Razorpay/UPI) + personas | 🟡 Feasible incrementally | business setup (Razorpay acct, pricing) |
| WhatsApp property watch | 🟡 Webhook feasible | WhatsApp BSP account + the SAR watch backend |

✅ done · 🟡 feasible now (no new infra/data) · 🔴 blocked on infra/data/licensing

## 5. What's already shipped that maps to this blueprint

Our recent work is genuinely the first real slices of Modules C & E: CRZ coastline screening, the live
waterlogging nowcast with official NDMA/IMD alerts, and US FEMA flood. The blueprint validates the
direction — we're on it, just at a scale the current stack supports.

## 6. Recommended near-term slice (Vercel-safe, open/licensed data, no Docker)

Everything here is 🟡 — real progress toward the vision with **zero new infra, zero credentials, zero
licensing risk**:

1. **"Evidence & Underwriting" drawer** on the web app — reorganize existing flood/scarcity/contamination/
   CRZ/nowcast outputs into an expandable, unit-and-source-cited panel (the doc's "credible & legible"
   UI). Pure frontend.
2. **Survey-number / ULPIN lookup field** in search — accept it, parse it, and return an honest
   "parcel data source pending authorized access" state. Ships the UX rail now; wires to API Setu later.
3. **Build Scope (TNCDBR) calculator as a pure-math module** — FSI / setbacks / coverage / height caps
   from user-entered plot area + road width + use. No spatial data needed; it's deterministic rule tables.
   This is the single highest-value cadastral feature we can build *without* parcel data.
4. **Consented document upload UX** (store only, OCR deferred) — the drag-drop + consent flow, so the
   product is ready the day we have an OCR host.

## 7. What must happen off-keyboard before the 🔴 items can start

These are **your** calls / accounts, not coding:
- NASA Earthdata + ISRO Bhoonidhi accounts (free, but gated).
- API Setu / DoLR authorized-consumer onboarding (business + legal process).
- A real backend host beyond Vercel: managed Postgres (with PostGIS/pgvector), an object store (S3/R2), a
  queue, and — for GeoFM/InSAR — a GPU cloud. Rough spend to run the orbital stack meaningfully is
  **four figures/month minimum**, before data costs.
- Razorpay (live), a WhatsApp BSP, and finalized pricing for the commercial tiers.

## 8. Decision needed

Pick the scope and I'll proceed:
- **(A) Build the feasible slice now** (§6) — recommended. Advances the blueprint on the current stack.
- **(B) Save an adapted `CLAUDE.md`** that encodes the vision *and* these constraints, as the repo's
  north-star doc, then do (A).
- **(C) Plan a real new backend** (separate repo/service) for the 🔴 orbital/cadastral engine — design
  first, since it can't live on Vercel.
