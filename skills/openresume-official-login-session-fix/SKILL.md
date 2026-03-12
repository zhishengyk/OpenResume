---
name: openresume-official-login-session-fix
description: Fix and extend OpenResume official-site login completion flows when a user can log into a careers site but the desktop app stays spinning, fails to mark login success, or misclassifies a valid session as logged out. Use when adjusting backend automation under backend/openresume_api/automation/ and backend/openresume_api/main.py, especially to reuse the existing completion-callback plus check_session pattern before adding site-specific patches.
---

# OpenResume Official Login Session Fix

Use this skill for official-site account-pool login bugs where the browser can reach a signed-in state but OpenResume does not stop loading or does not persist `is_logged_in`.

## Default approach

Prefer small reuse-oriented changes.

- Reuse the generic login completion flow in `backend/openresume_api/main.py` and `backend/openresume_api/automation/playwright_runtime.py` before adding company-specific logic.
- Treat window close as a fallback only. Success should be driven by a real session probe.
- Reuse `driver.check_session(...)` as the source of truth for "logged in" whenever possible.
- Only add site-specific detection when the generic probe still misclassifies a real signed-in page.

## Fast diagnosis

Check these files first:

- `backend/openresume_api/main.py`
- `backend/openresume_api/automation/playwright_runtime.py`
- `backend/openresume_api/automation/official_drivers.py`
- `src/pages/AccountPoolPage.tsx`
- `backend/tests/test_official_account_pool.py`

Look for these failure modes:

- Login request waits forever because `interactive_run()` only resolves on browser close or timeout.
- `check_session()` uses weak page-text heuristics and marks a real signed-in page as logged out.
- The site redirects away from `/login`, but the code still searches the HTML for login text markers.
- Frontend disables the login button when no default account exists.

## Repair workflow

### 1. Fix completion at the runtime/main layer first

If the spinner never stops after a real login:

- Keep `interactive_run()` interactive.
- Add a `completion_callback` hook that periodically saves `storage_state`.
- In `main.py`, pass a callback that runs `playwright_automation_runtime.inspect(...)`.
- Inside that inspect call, reuse `driver.check_session(...)`.

This keeps the completion rule generic and avoids per-site window hacks.

### 2. Strengthen `check_session()` before adding site-only code

If a site really is signed in but still fails the probe:

- Prefer recognizing redirect-away-from-login as a positive signal when the target URL is a login page and the current URL is no longer a login-like URL.
- Keep captcha detection as a hard failure.
- Avoid broad text-only checks as the sole signal on modern SPAs.

For small fixes, patch `GenericOfficialDriver.check_session()` instead of introducing a custom driver.

### 3. Only then add site-specific logic

Site-specific logic is justified when:

- The site stays on a login-like URL even after auth.
- The signed-in state is only visible via a stable selector or profile widget.
- The generic redirect/content heuristics are insufficient.

Keep the site patch minimal and local to `official_drivers.py`.

## Reuse rules

If the new bug is close to a previous one, do not add a new workflow.

- Reuse `completion_callback` polling for "still spinning after successful login".
- Reuse redirect-aware `check_session()` for "logged in but reported logged out".
- Reuse frontend auto-provision of a default account for "login button disabled with no account".
- Only create a new helper if the same patch would otherwise be repeated in 2 or more places.

## Verification

Prefer lightweight checks first:

- `npm.cmd run typecheck`
- `python -m py_compile backend\\openresume_api\\automation\\base.py backend\\openresume_api\\automation\\playwright_runtime.py backend\\openresume_api\\automation\\official_drivers.py backend\\openresume_api\\main.py`

If tests are available and the local test DB is not locked, run targeted account-pool tests in `backend/tests/test_official_account_pool.py`.

If `pytest` is blocked by a locked SQLite test DB, fall back to:

- `py_compile`
- a minimal one-off script that calls `driver.check_session(...)` with a fake page
- direct inspection of the `git diff`

## Notes

- Keep the frontend hint accurate: the app opens the official page and caches session state only.
- If you change the runtime method signature, update test doubles in `backend/tests/test_official_account_pool.py`.
