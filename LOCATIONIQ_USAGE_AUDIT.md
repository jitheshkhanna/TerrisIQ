# LocationIQ Usage Audit & Optimization

_Read-only audit → root cause → fixes. Verified against the live code on 2026-10-02._

## 1. Executive summary
LocationIQ is called from **exactly one place** — the backend `_locationiq()` in `/api/v1/geocode?fast=1`, one HTTP GET per call, **no retry logic**, with automatic Photon fallback on any error. The key is **server-side only**. There are **no infinite loops, no retry storms, and no cross-surface duplicate geocoding**. The ~177 requests over Oct 1–2 are dominated by **developer/testing traffic** (the key went live Oct 1) plus **autocomplete firing one call per debounced keystroke**. Fixes reduce per-search calls (higher threshold + debounce + client cache) and add a 429 circuit breaker; none required an architecture change.

## 2. Current LocationIQ usage
- **Endpoint used:** `GET https://api.locationiq.com/v1/autocomplete` (forward, type-ahead). No reverse, maps, or routing.
- **Purpose:** address → ranked suggestions (with coords), city-biased, India-only.
- **Caller:** backend `/geocode?fast=1` only. Key read from `LOCATIONIQ_KEY` env.

## 3–6. The 177 / Oct-1 130 / Oct-2 47 / 8 rate-limited
The LocationIQ key was added **Oct 1** — the dashboard shows zero before that, so 100% of the 177 is post-integration. Breakdown (by code behaviour + timeline):
- **Developer & verification traffic** — the dominant share. Oct 1–2 was the speed-debugging + LocationIQ integration + verification window; dozens of direct `curl`/browser geocode calls were made (many in bursts).
- **Autocomplete per keystroke** — each debounced keystroke (≥2 chars, 160–220ms) = one call; a typed search ≈ 2–5 calls.
- **8 rate-limited:** LocationIQ free tier ≈ **2 req/s**. Bursts (fast typing or back-to-back test curls) exceed it → HTTP 429. Each 429 fell back to Photon and still returned results. **No retry followed a 429** (confirmed in code), so there was no amplification.

## 7. Exact request flow
```
Extension popup / Web app SearchBar
  └─ type ≥3 chars ─(debounce)→ /api/v1/geocode?fast=1   ─→ LocationIQ (1 GET)
                                     │ 429 / error / empty ─→ Photon (fallback, no retry)
  └─ pick a suggestion ──────────→ /api/v1/risk (lat,lng)  [NO geocode]
  └─ "See full report" deep link ─→ web app ?lat&lng&city  [NO geocode — scores by coords]
Manual search (Enter on typed text) → /geocode?fast=1 (1) → /risk
```

## 8–13. Requests per analysis, duplicates, cache
- **Per new autocomplete search (before fix):** ~2–5 LocationIQ calls (one per prefix typed). **Pick → risk: 0** geocode. **Deep link → web app: 0** (uses coords).
- **Repeat of same query:** extension popup = **0** (session `geoCache`); web app = **1** (no client cache) — now fixed.
- **No frontend+backend double geocode:** the client never calls LocationIQ; only the backend does, once per `/geocode`.
- **No extension→web-app duplicate:** deep link carries coordinates.
- **Cache:** backend in-memory `_cache` (per serverless instance, ephemeral) keyed by `expand_query(raw).lower() | limit | city | fast`. Casing/whitespace normalized via `strip()` + `expand_query` + `.lower()`. Effective within an instance; limited across cold starts.

## 14. LocationIQ limits (free "GeoLite" tier)
~**2 requests/second**, **5,000 requests/day**. Attribution required (OSM/LocationIQ). Our volume is far under the daily cap; the only pressure is the per-second burst limit, now handled by the circuit breaker + fallback.

## 15–17. Retry / rate-limit / error handling
- **No retry of LocationIQ** by design — any failure (429/4xx/5xx/timeout/malformed) → **immediate Photon fallback** (users still get results). This is better UX than retrying a rate-limited endpoint.
- **New: 429 circuit breaker** — a 429 opens a 15-second cooldown during which `/geocode?fast=1` skips LocationIQ and serves Photon directly, so a burst never keeps hitting a rate-limited endpoint.
- **4xx (bad input/credentials):** not retried; falls to Photon or returns a clean empty/"no results" state.

## 18. Security — API key
- `LOCATIONIQ_KEY` is read only from backend env; **not present in the extension or web-app source or bundles** (grep-verified). The extension/web app reach LocationIQ only *through* the backend. ✅

## 19–20. Observability
Lightweight and privacy-conscious: the backend already distinguishes `source: "locationiq"` vs `"photon"` per response, so cache/fallback behaviour is visible without logging user addresses. No third-party analytics added.

## Fixes implemented
| Priority | Fix | File |
|----------|-----|------|
| P1 | Autocomplete threshold 2→**3 chars**, debounce →**280–300ms** | `popup.js`, `SearchBar.tsx` |
| P1 | **Client-side geocode cache** added to the web app (extension already had one) | `SearchBar.tsx` |
| P1 | **429 circuit breaker** (15s cooldown → Photon) | `geocode.py` |
| ✓ | Verified: no retry storm, key server-side, no cross-surface dup | — |

## Before / after (per new autocomplete search)
- **Before:** ~2–5 LocationIQ calls; repeats on web app = 1.
- **After:** ~1–2 LocationIQ calls (fewer prefixes trigger at ≥3 chars); **repeats = 0** (both surfaces cached); bursts that 429 stop hitting LocationIQ for 15s.
- **Pick + deep link:** 0 geocode (unchanged — already optimal).

## Remaining risks / next steps (optional)
- Backend cache is per-instance/ephemeral on serverless. If volume grows, a shared cache (e.g., Vercel KV) would raise hit-rate — **not needed at MVP scale** (well under 5,000/day).
- `api.terrisiq.com` could front the backend so the extension references only branded origins (cosmetic; current setup is fine).
- Free tier (5,000/day) comfortably covers MVP; revisit only if daily usage approaches a few thousand.
