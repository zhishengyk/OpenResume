# Diagnostics

## Fast triage

- `fetch_error` first: verify environment connectivity before changing extractor code.
- `candidate_count = 0`: inspect the entry page, redirects, provider fingerprint, and whether the smoke script is passing the correct `source_kind` and readable job targets.
- `hard_filtered > 0`: inspect sampled titles and URLs; the extractor is probably scraping category or navigation cards.
- `detail_dropped > 0`: inspect detail-page classification and whether the fetched page is still a shell.

## Typical fixes

- Homepage only: follow the search, tab, share, or referral page first.
- SSR shell: inspect embedded JSON and lazy chunks for the real API.
- Custom JS site: inspect bundles for AJAX endpoints and token handling.
- Known-good site returns zero only in smoke: make the script reuse `official_sources.py` classification and retry with broad role families.
- Over-filtering suspicion: confirm the page is truly a job detail before touching quality rules.
