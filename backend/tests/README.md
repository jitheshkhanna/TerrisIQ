# QA suite

Two runnable suites. Both take a base URL, defaulting to a local server.

```bash
python tests/test_api_contract.py                                  # local
python tests/test_api_contract.py https://chennai-terra-risk.vercel.app
python tests/test_answer_quality.py https://chennai-terra-risk.vercel.app
```

**`test_api_contract.py` (134 checks)** — the contract. Every city scores, weights sum
to 1, unavailable dimensions are null *and* absent from the weights, grade bands are
exact at every boundary (20/21, 40/41, 60/61, 80/81), bad input is refused, geocoding
returns results inside the requested city, layers serve per city, PDFs render.

**`test_answer_quality.py` (40 checks)** — whether the answers are *right*, which a
200 response does not tell you. Known-bad plots must outscore known-good ones in the
same city; the severity floor and evidence ceiling must actually fire; the composite
must equal the renormalised weighted sum; ward resolution is checked against known
ground truth (Velachery is Ward 177, Kurla is Ward L, Abids is in GHMC's Abids ward);
bbox corners score; concurrent requests hold up.

## Bugs these caught

- **Geocoding was dead in seven of eight cities.** `in_region()` still hard-coded
  Chennai's bounding box after the multi-city refactor, so every Bengaluru, Mumbai,
  Delhi, Pune, Hyderabad, Kolkata and Ahmedabad result was silently discarded. The
  endpoint returned HTTP 200 with an empty list, so nothing looked broken.
- **A mismatched city was accepted.** Posting Chennai coordinates with `city=mumbai`
  scored the plot against Mumbai's layers and returned a confident, meaningless grade.
  It now returns 422 naming the city the point is actually in.
