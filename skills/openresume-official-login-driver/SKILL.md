---
name: openresume-official-login-driver
description: Extend OpenResume account-pool official sites and login drivers for company career portals. Use when Codex needs to add or validate official_sites descriptors, reverse-engineer a company login surface, choose between direct login pages, homepage click triggers, or Alibaba-style embedded login widgets, and add matching tests for account-pool session caching.
---

# OpenResume Official Login Driver

Use this skill when the request is about account-pool login support for official career sites, not about job list scraping.

## Workflow

1. Start from the live company homepage or known login URL.
2. Classify the login surface before editing code:
   - `direct`: stable standalone login URL
   - `click`: homepage button or link opens the login layer
   - `alibaba_embed`: page loads `MiniLoginEmbedder` or related Alibaba login shell
3. Patch both layers together:
   - `backend/openresume_api/services/official_sites.py`
   - `backend/openresume_api/automation/official_drivers.py`
4. Keep `company_key` aligned with `career_collectors/manifest.py` collector keys.
5. Add or update focused tests in `backend/tests/test_official_account_pool.py`.

## Site Classification Rules

- Use `direct` when a stable `/login` route or SSO page opens without needing a homepage click.
- Use `click` when the live entry point is a visible homepage control and direct `/login` is missing, unstable, or redirects away.
- Use `alibaba_embed` when the page ships Alibaba login widgets such as `MiniLoginEmbedder`, `mini-login-embedder`, or Havana/Alipay login assets.

## Where To Patch

- `official_sites.py`
  - one descriptor per company collector key
  - include `login_url`, `session_check_url`, `source_sites`, `supported_variants`, and aliases
- `official_drivers.py`
  - keep launch logic generic and mode-based
  - prefer reusable selector groups over one-off branches
- `test_official_account_pool.py`
  - assert `/api/official-sites` covers every manifest company
  - assert each company launches with the expected strategy

## Validation

- Run `python -m pytest backend/tests/test_official_account_pool.py -q`
- Run `python -m pytest backend/tests/test_api.py -k "guided_apply_requires_consent_and_uses_listing_id or test_disclaimer_flow" -q`
- Run `npm run typecheck`

## Pitfalls

- One `company_key` may span multiple domains. Document the risk if login state is not obviously shared.
- Prefer homepage click triggers over guessed hidden routes when the route redirects back to home.
- For Alibaba-family sites, do not invent a fake `/login`; inject the official embedder on the real page.
- If a click selector disappears, fail loudly in the driver instead of silently pretending login opened.
