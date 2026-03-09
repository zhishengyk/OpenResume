# Provider Patterns

## ByteDance ATSX

- Fingerprints: `jobs.bytedance.com`, `atsx`, `script#js-websiteInfo`, Feishu CDN chunks, large campus payloads.
- Treat `https://jobs.bytedance.com/` as an entry page. It often links to share or keyword pages under `/campus/position?...` or `/experienced/position?...`.
- Prefer the canonical list page `https://jobs.bytedance.com/campus/position` before trusting share-page query params. A signed API can return `200` with zero jobs if the inherited keyword is stale or over-filtered.
- Real list API:
  - `POST /api/v1/search/job/posts?...&_signature=...`
  - first call may return `405`
  - then request `POST /api/v1/csrf/token` with `{"portal_entrance":1}`
  - retry list or detail with `x-csrf-token` plus cookies
- Required cookies are lightweight. Random non-empty `s_v_web_id` and `device-id` values worked, together with `channel=campus`, `platform=pc`, and the returned `atsx-csrf-token`.
- Real detail API:
  - `GET /api/v1/job/posts/{id}?portal_type=3&source_job_post_id={id}&with_recommend=false&_signature=...`
- Good patch shape:
  - homepage -> canonical `/campus/position`
  - load sign chunk from page HTML
  - compute `_signature`
  - obtain CSRF token
  - fetch list JSON
  - fetch detail JSON in `prepare_detail_page`

## Taobao or Taotian campus site

- Fingerprints: `zhaopin.taobao.com`, redirects into `talent.taotian.com`, custom JS shell, `__token__` embedded in HTML.
- Treat `zhaopin.taobao.com` as an entry page only.
- Real list pages live under:
  - `https://talent.taotian.com/campus/position-list?campusType=freshman&lang=zh`
  - `https://talent.taotian.com/campus/position-list?campusType=internship&lang=zh`
- Extract `__token__` from the page, then call:
  - `POST /searchCondition/list?_csrf=...`
  - `POST /position/search?_csrf=...`
- Keep directory filtering on. The right fix is to land on `position-detail?positionId=...`, not to admit `position-list` or older category pages as jobs.
- Useful payload fields include title, description, position id, and city or location text. Use payload detail extraction when the detail HTML is still thin.

## PDD campus shell

- Fingerprints: `careers.pddglobalhr.com`, sparse Next-like shell page, campus tabs, empty first-response HTML.
- Do not stop at `https://careers.pddglobalhr.com/campus`.
- Follow the real scope pages:
  - `https://careers.pddglobalhr.com/campus/grad`
  - `https://careers.pddglobalhr.com/campus/intern`
- Real APIs:
  - grad list: `POST /api/careers/api/recruit/position/list`
  - intern list: `POST /api/careers/api/recruit/position/train/list`
  - detail: `POST /api/careers/api/recruit/position/detail` with `{"id": positionId}`
- Build real detail URLs such as `/campus/grad/detail?positionId=...` or `/campus/intern/detail?positionId=...`, then enrich with detail JSON.

## Next.js or JSON SSR shells

- Inspect `__NEXT_DATA__`, route config, and lazy-loaded chunks.
- If page props are empty, search loaded chunks for `api/` paths, tab routes, or `router.push` targets.
- Follow secondary routes such as `/grad`, `/intern`, or tab-specific pages before concluding that the site has no jobs.

## General heuristics

- `candidate_count = 0` usually means the wrong page level, the wrong extractor hint, or a provider-specific token or signature flow that has not been replicated yet.
- A large hard-filter count usually means cards were found, but they are directories, navigation items, or off-target roles.
- A nonzero candidate count followed by detail drops usually means detail classification or provider-specific detail parsing is incomplete.
- When a smoke script says zero on every known-good extractor, verify that the script uses the same source classification logic as `official_sources.py` and that requested job targets are not corrupted.
