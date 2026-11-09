<!-- Thanks for contributing to TerrisIQ! Keep the PR focused. -->

## What this does

<!-- One or two sentences. Link the issue it closes, e.g. "Closes #12". -->

## How I tested it

<!-- Commands you ran, points you scored, before/after. -->

## Checklist

- [ ] The change is focused and matches the surrounding code style.
- [ ] Backend offline tests pass: `cd backend && python -m pytest tests/test_build_scope.py tests/test_golden_points.py -q`
- [ ] Frontend is clean: `cd frontend && npx tsc --noEmit && npm run lint`
- [ ] If I added a backend field, I extended `schemas.py` **and** `frontend/src/lib/api.ts` together.
- [ ] If I touched a risk engine, I added/updated a test and verified the math.
- [ ] No secrets committed; any new dependency is justified (250 MB backend budget).

## Guardrails (see CONTRIBUTING.md)

- [ ] No scraping of restricted government portals.
- [ ] Any new dataset is open-licensed or authorized, and is listed in the README + `NOTICE`.
- [ ] Every new number shows its units and source; thin/missing data never reads as "safe".
