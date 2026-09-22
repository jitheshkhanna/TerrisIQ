# Terrisiq — Session Handoff (continue from mobile)

_Last updated: 2026-09-22_

Paste this whole file into a new Claude chat (mobile web or app) to bring it up to speed.

## What this project is
Terrisiq — a browser extension that shows environmental risk (flood, groundwater
contamination, water scarcity) for a property directly on real-estate sites
(Google Maps, NoBroker, 99acres, MagicBricks, Housing) plus a Next.js web app.

- **Frontend:** Next.js 16.3.3 (App Router), deployed at https://chennai-terra-risk.vercel.app
- **Backend:** Python API on Vercel (chennai-terra-risk-api)
- **Extension:** Manifest V3, name "Terrisiq — Property Risk Intelligence",
  slogan "The risk IQ every listing is missing."
- **Coverage:** 8 tier-1 Indian cities; Chennai flood layer from a validated
  municipal survey (7,453 polygons).

## Where things stand
- Extension renamed Terris → Terrisiq across manifest, popup, content card.
- Clean submission zip built: `~/Desktop/terrisiq-v0.1.0.zip` (manifest + icons + src only).
- Privacy policy page built and **deployed live**:
  https://chennai-terra-risk.vercel.app/privacy
- Chrome Web Store draft in progress.

## Chrome Web Store — remaining steps (Privacy practices tab)
1. Remote code → "No, I am not using remote code"
2. Data usage → check **Location** only
3. Certification → check all three boxes
4. Privacy policy URL → `https://chennai-terra-risk.vercel.app/privacy`
5. Save draft → Submit for review

## Still to do
- Store screenshots (1280×800 PNG, ≥1 required) — AI prompts already drafted.
- Branded 128×128 store icon.
- Backend hardening: rate-limit by IP + origin/referer allowlist before promoting.

## Local toolchain notes
- No Docker / Homebrew / GDAL. System Python 3.9 only.
- `backend/data/` holds ~257 MB of GIS files (may be gitignored — see repo).
