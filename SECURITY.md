# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Report it privately through GitHub's
[Report a vulnerability](../../security/advisories/new) (Security → Advisories), or
email **security@terrisiq.com**.

Include enough to reproduce it: the affected endpoint or component, steps, and the
impact you observed. We aim to acknowledge within 72 hours and to keep you updated as
we work on a fix. Please give us a reasonable window to release a fix before any public
disclosure.

## Scope

This repository is the TerrisIQ web application: a FastAPI backend (`backend/`) and a
Next.js frontend (`frontend/`). Things we especially want to hear about:

- Leaked or hard-coded secrets (API keys, tokens).
- Ways to make the app log, store, or expose a user's consented uploaded document.
- Ways to read a risk score or report as authoritative when the underlying data is thin
  or missing (a correctness-as-safety issue — see the provenance guardrail).
- Server-side request forgery, injection, or auth-gate bypass on the API.

## Secrets

All keys live in server-side environment variables only; none are committed. See
`backend/.env.example`. If you believe a secret was ever committed, report it as above
and treat it as compromised — rotate it immediately.

## Supported versions

This is an actively developed project. Fixes land on `main`; please test against the
latest `main` before reporting.
