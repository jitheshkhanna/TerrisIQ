# TerrisIQ — QA & E2E Test Report

_Date: 2026-11-01. Scope: live terrisiq.com (web) + chennai-terra-risk-api (backend), India + US.
Driven manually end-to-end (browser) + API probes. No automated suite exists yet (see scores)._

## Use-case scenarios covered
1. **US investor** checks a US property (Miami, New Orleans, Denver) → flood risk from FEMA.
2. **India buyer** checks a Chennai property → flood + groundwater + scarcity.
3. **Landing** → auto-geolocate to the visitor's location (maps-app style).
4. **Mobile** → drag the bottom sheet (peek 80/20 ↔ full).
5. **Global search** → type a place anywhere ("Miami").
6. **Download report** (PDF) for India and US points.
7. **Ask-about-this-place** chat for India and US points.
8. **Map layers** toggle (Flood / Water / Industry / None).
9. **Edge**: gibberish search, US point outside FEMA coverage, FEMA outage.

## Bug sheet

| ID | Title | Area | Severity | Priority | Status | Notes / repro |
|----|-------|------|----------|----------|--------|---------------|
| B1 | Search is India-only; "Miami" returns Indian matches | Backend geocode | High | P0 | **Fixed (deploy pending)** | `countrycodes=in` + hardcoded Chennai viewbox/`bounded` + `", Chennai"` appended. Removed; results now global, city bbox is a soft bias only. |
| B2 | "Download report" fails (HTTP 422) for US points | Backend report | High | P0 | **Fixed (deploy pending)** | `/report` used `resolve_city` (India-only) → 422. Added US branch (`us_assess`). |
| B3 | US PDF would crash / draw a Chennai mini-map | Backend PDF | High | P0 | **Fixed (deploy pending)** | `build_report` fell back to Chennai for `city="us"`; `city.name` derefs crashed on None. Now skips the locality map and uses the result's name for out-of-India points. Verified: US PDF 8.5KB, India 513KB. |
| B4 | Map-layers panel shows India legend ("Inundation zones", Flood/Water/Industry) for US points | Frontend map | Medium | P2 | Open | The hazard layers/legend are Chennai's; for a US point they're meaningless (FEMA is a point lookup, not a tile layer). Should hide/relabel the layer controls when the scored place is US. |
| B5 | US report page-2 text is India-flavoured ("ask neighbours what depth their borewell runs at") | Backend PDF | Low | P3 | Open | The "not scored" copy for contamination/scarcity is written for India. Harmless but reads oddly on a US report. |
| B6 | Auto-geolocate shows no "allow location" affordance if the user dismisses the prompt | Frontend | Low | P3 | Open | By design it falls back to the default area silently; the manual locate button is the recovery. Acceptable, noted. |
| B7 | CityPicker removed, so no visible place/label for US beyond the card | Frontend | Low | P3 | Won't-fix | Intended (search now global). The card states "United States"; a header place-name could be added later. |

Fixed in this pass: **B1, B2, B3** (all P0). Code committed; **production deploy was blocked by the environment this turn**, so they are not yet live.

## Test scores (honest, post-fix where fixed)

| Dimension | Score /10 | Basis |
|-----------|-----------|-------|
| Functionality (E2E) | 8 | Core India + US flows work: card, map-follow, search (after B1), sheet, report (after B2/B3), chat. US is flood-only by design. |
| Usability / UX | 8 | Clean, mobile sheet with snap, auto-geolocate, readable glass. Dinged for B4 (misleading US layers). |
| Compatibility (desktop + mobile) | 8 | Verified 1280×800 and 390×780, light theme. Not tested: real iOS Safari, small Android, dark. |
| Accessibility | 7 | WCAG-measured colour system, 44px taps, focus rings kept. Not formally audited (no axe run); glass contrast held at 0.96 over map. |
| Performance | 7 | Geocode cached; FEMA is slow/flaky (retry + safe-degrade added). Risk: FEMA latency/throttle under US volume — add a short cache next. |
| Regression | 3 | India flows verified unaffected **manually**; there is **no automated regression suite**, so this is the real risk, not the code. |
| Automation | 1 | **No test suite exists** (no pytest, no Playwright). This is the biggest gap. Recommend: pytest for `us_flood`/`scoring` engines + one Playwright smoke (India + US happy path). |
| Security | 6 | Optional API-key gate; open government data; no secrets in client. Not pen-tested; CORS and rate-limits are basic. |

**Headline:** the product is functionally solid for India + US flood once B1–B3 deploy. The weakest areas are **automation and regression coverage** (there is none) — that's where the next investment should go, because it's what makes "fix everything and know it stays fixed" possible.
