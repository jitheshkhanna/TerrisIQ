# Contributing to TerrisIQ

Thanks for wanting to help. TerrisIQ is parcel-level property and climate-risk
screening — honest, cited, and careful about what runs where. Contributions are
welcome, from a typo fix to a new risk engine.

Please read the **[Guardrails](#guardrails-read-before-you-build)** below before
writing code. They are not style preferences — a few of them are legal and ethical
lines that got an earlier version of this project pulled from the Chrome Web Store.

---

## Ways to contribute

- **Report a bug or a wrong number** — open an issue with the coordinates/input and
  what you expected. For risk scores, tell us the source you're checking against.
- **Suggest a feature** — open a feature-request issue. Small, focused proposals move
  fastest.
- **Fix or build** — comment on an issue to claim it (or open one first for anything
  non-trivial), then send a pull request.
- **Improve data coverage** — see the coverage table in the README. New cities need a
  *licensed or open* source; see guardrail 2.

Good first issues are labelled [`good first issue`](../../labels/good%20first%20issue).

---

## Local setup

Full instructions are in the [README "Quick start"](README.md#quick-start). In short:

```bash
# Backend (FastAPI, :8000)
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Frontend (Next.js, :3000) — in another terminal
cd frontend && npm install && npm run dev
```

The app runs with **no API keys** for the core risk flow. Optional keys (Gemini chat,
LocationIQ geocoding) go in a local `.env` — copy `backend/.env.example` and
`frontend/.env.local.example`. Never commit a real key (see guardrail 6).

The heavy GIS data under `backend/data/` is git-ignored and rebuilt locally with
`cd backend && make data`. The app imports and the unit tests run without it.

---

## Running the checks

CI runs these on every pull request; run them locally first.

```bash
# Backend — offline unit tests (no data/ or network needed)
cd backend && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests/test_build_scope.py tests/test_golden_points.py -q

# Frontend — type-check and lint
cd frontend && npx tsc --noEmit && npm run lint
```

The integration suites (`test_api_contract.py`, `test_answer_quality.py`) need a
running API with the data pipeline built; run them locally when you touch scoring,
but CI does not.

When you change a risk engine, **verify the math before wiring UI** and add or extend
a test in `backend/tests/`.

---

## Pull request process

1. Fork, then branch from `main`: `feat/short-name` or `fix/short-name`.
2. Keep the change focused. Match the surrounding code — module docstrings that explain
   the *why*, honest comments about data limits, lean dependencies.
3. If you add a backend field, extend both `RiskResponse` in
   `backend/app/models/schemas.py` **and** the matching interface in
   `frontend/src/lib/api.ts`, together.
4. Run the checks above. Green locally, green in CI.
5. Open the PR and fill in the template. Link the issue it closes.

A maintainer reviews every PR. Be patient and responsive to review comments.

---

## Guardrails (read before you build)

These are non-negotiable. A PR that crosses one of them will be declined regardless of
how good the code is. The full rationale is in [CLAUDE.md](CLAUDE.md).

1. **No scraping of restricted government portals.** Never write code that defeats
   CAPTCHAs, session tokens, or rate limits on transactional portals (TNREGINET, Tamil
   Nilam, Bhu-Naksha, and the like). Cadastral/title data comes only from official
   federated gateways under proper onboarding, open spatial portals, user-consented
   document uploads, or AI delineation from licensed imagery.
2. **Confirm a dataset's license before building on it.** Absence of a license is not
   permission. New data sources must be open-licensed or accessed under an authorized
   API. Add the source and its license to the README and `NOTICE`.
3. **Provenance and units on every number.** Every quantitative metric and AI answer
   exposes its physical units and cites its source. Thin or missing data is labelled by
   confidence tier — it must **never read as "safe."** The AI answers only from computed
   data and admits what it doesn't know.
4. **Privacy on consented uploads.** User documents (patta, EC, FMB) hold personal data.
   Uploads are explicit opt-in, used only to serve that user's report, and never logged
   or exposed.
5. **Keep the licensing clean-room intact.** GPL-3.0 tools (MintPy, PyAPS, PySolid) are
   never imported or bundled into this repository; they belong to an isolated Phase B
   worker only. Core services stay on permissive licenses.
6. **No secrets in the client or the repo.** Keys live in server environment variables
   only. If you ever commit one by accident, tell us (see [SECURITY.md](SECURITY.md)) and
   assume it is compromised.
7. **Respect the serverless budget.** The backend ships into a 250 MB Vercel bundle.
   Justify every new dependency by the megabyte; prefer pure-Python.
8. **Don't recolor the hazard ramp.** The WCAG-measured risk colors and the map UI are
   fixed; brand orange is card chrome only.

By submitting a contribution you agree it is licensed under the project's
[Apache-2.0 License](LICENSE), and you follow our [Code of Conduct](CODE_OF_CONDUCT.md).
