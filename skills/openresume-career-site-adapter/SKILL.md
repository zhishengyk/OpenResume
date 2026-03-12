---
name: openresume-career-site-adapter
description: Adapt official recruitment and career homepages into reliable job extraction flows in OpenResume. Use when Codex needs to reverse-engineer a company careers site, decide whether the supplied URL is only an entry page, discover secondary listing or detail APIs, map variants into the official career collector architecture (manifest -> company collector -> provider), or explain why a live site returns zero usable jobs.
---

# OpenResume Career Site Adapter

Use this skill to turn a company career homepage into real job detail extraction without weakening the existing quality gates.

## Workflow

1. Reproduce the failure on the exact homepage the user supplied. Treat that URL as an entry page, not proof that it is the real job list.
2. Fingerprint the provider before editing code. Inspect redirects, script ids, embedded JSON, JS bundle names, and obvious route fragments.
3. Discover the next hop. Many sites hide jobs behind category pages, referral pages, share pages, tabs, or APIs that are not linked as direct detail pages.
4. Patch the narrowest layer that fits the problem. Put transport and pagination logic in `career_collectors/providers/`, source-specific field mapping in `career_collectors/companies/`, and source declarations in `career_collectors/manifest.py`.
5. Add a fixture for the newly discovered payload or page shape, then rerun live smoke plus pytest.

## Provider Checkpoints

- ByteDance ATSX: prioritize the canonical `/campus/position` list page over noisy share or keyword pages, then use the signed campus APIs for real list and detail payloads.
- Taobao or Taotian: treat `zhaopin.taobao.com` as an entry only. Move to `talent.taotian.com/campus/position-list`, obtain the page token, then call the real search endpoints.
- Aliyun careers: treat `careers.aliyun.com` as a Taotian-like shell with circle-specific channels. Extract `__token__` from HTML, then call `/searchCondition/list` and `/position/search` on the same domain using `_csrf` query + `x-csrf-token`.
- Alibaba holding: `talent-holding.alibaba.com` is the same Alibaba careers shell as Taotian/Aliyun. Reuse a shared Alibaba provider and swap only `base_url`, `channel`, and detail/list entry URLs.
- Meituan official campus: the homepage is a shell. The real APIs are `POST /api/official/job/getJobList` and `POST /api/official/job/getJobDetail` on `zhaopin.meituan.com`. The list payload uses `page.pageNo`, `page.pageSize`, and `keywords`.
- PDD shell pages: follow `/campus/grad` and `/campus/intern` before concluding the page is empty. The real jobs live behind JSON APIs, not the first HTML response.
- PDD campus detail: the visible relative paths in chunks are misleading. The real list/detail endpoints are under `/api/careers/api/...`, for example:
  - campus: `POST /api/careers/api/recruit/position/list`
  - internship: `POST /api/careers/api/recruit/position/train/list`
  - detail: `POST /api/careers/api/recruit/position/detail`
- Tencent dual-site model:
  - `careers.tencent.com` uses `GET /tencentcareer/api/post/Query` with variant attrs (`experienced=1`, `campus=2,5`, `internship=3`), `pageSize<=50`, and possible `gb18030` payloads.
  - Chinese keywords can under-recall on `careers.tencent.com`; expand role keywords with stable English aliases (for example `frontend engineer`) before judging zero results.
  - `join.qq.com` is campus-focused and should be merged into Tencent campus/internship collection via `GET /api/v1/position/getProjectMapping` and `POST /api/v1/position/searchPosition`.
  - Prefer `projectMappingIdList` from mapping API over guessing `projectId`.

## Where To Patch

- `backend/openresume_api/career_collectors/manifest.py`
  Use for source keys, company labels, variant declarations, and entry/source domains.
- `backend/openresume_api/career_collectors/companies/{company}.py`
  Use for collector orchestration and `CollectedJobRecord` mapping.
- `backend/openresume_api/career_collectors/providers/{provider}.py`
  Use for provider-specific HTTP flow, auth/token/csrf/signature handling, pagination, decoding, and dedupe.
- `backend/openresume_api/adapters/official.py`
  Use only for source filtering, run summary wording, and final platform-level dedupe/guardrails.

## Recruitment Type Variants

All adapters must support three standard recruitment types. Use `$openresume-recruitment-variants` skill for details.

| Variant | Label | Description |
|---------|-------|-------------|
| `experienced` | 社招 | Social recruitment for experienced professionals |
| `campus` | 校招 | Campus recruitment for fresh graduates |
| `internship` | 实习 | Internship for current students |

When adding a new company source, define all three variants in `manifest.py` if the site supports them.

## Rules

- Start from the homepage and assume it may only contain links to the real search pages.
- Prefer structured payloads over brittle DOM scraping when both exist.
- Follow redirects and short links. Some providers expose jobs only through share or referral URLs.
- Search JS bundles for `api/`, router paths, and query builders when the HTML is just a shell.
- If a homepage links into a filtered share page, try the canonical unfiltered list page as well before accepting a zero-result API response.
- Do not relax hard filters to make a site look green. If everything is filtered as directory or noise, extraction is still wrong.
- Keep `raw_payload.quality` truthful so matching logic keeps working.
- Always define all three recruitment type variants (experienced/campus/internship) for each company source.
- If a company already has a collector, prefer adding a new provider into that collector for incremental sources instead of creating a new company collector.

## Notes From 2026-03-11

- When multiple Alibaba-group sites share the same shell, extract a reusable provider first. The stable seam is `base_url + variant channel config`; the token/csrf flow stays identical.
- Alibaba-shell payload fields are not fully uniform across brands:
  - Some sites require `key` (not `keyword`) for query text.
  - Off-campus requests often need extra empty filter fields (`batchId/categories/deptCodes/regions/subCategories`) to match browser behavior.
  - AMap/Eleme/AIDC social channels currently use `channel=group_official_site` in live requests.
- For PDD, do not trust the first relative `api/recruit/...` strings you see in the page chunks. Confirm the runtime network path; the actual browser requests prepend `/api/careers/`.
- For Meituan, the campus homepage does not itself prove campus-only filtering. Confirm the list/detail APIs first, then decide whether variant labeling is a site-level truth or just an entry-page label.
- Kuaishou has multi-channel intern flows:
  - `zhaopin.kuaishou.cn/#/official/trainee` uses the social API with `positionNatureCode=C002`.
  - `campus.kuaishou.cn` uses campus API `positionNatureCode=intern`.
  - Internship extraction should merge both channels and dedupe by job id.
- Kuaishou campus can legitimately return very low counts (for example fulltime=2, intern=1 at the time of validation); do not treat this as parser failure unless request parity is broken.
- JD campus detail endpoint uses `publishId` in `/api/wx/position/detail/{id}`. Using `reqId` may return structurally successful but empty bodies.
- Ant Group search currently returns empty when `pageSize` is too large in some flows; cap to small page size (for example `<=10`) before judging the source as empty.
- Xiaohongshu public jobs use:
  - `POST https://job.xiaohongshu.com/websiterecruit/position/pageQueryPosition`
  - `GET https://job.xiaohongshu.com/websiterecruit/position/queryPositionDetail?positionId=...`
  - `recruitType` values `social`, `campus`, and `intern`
  - The campus list can still expose internship titles, so campus vs internship may need title-based splitting when the list payload does not expose a cleaner flag.
- Bilibili requires a CSRF bootstrap before list calls:
  - `GET /api/auth/v1/csrf/token`
  - headers must include `X-AppKey`, `X-UserType`, and variant-specific `X-Channel`
  - list calls then need `X-CSRF`
  - campus fulltime and internship both use `/api/campus/position/positionList` but different `recruitType` values.
- Dewu is a dual-domain Feishu ATSX integration:
  - social uses `https://poizon.jobs.feishu.cn/index`
  - campus/internship uses `https://campus.dewu.com/`
  - both rely on `/api/v1/csrf/token`, `/api/v1/search/job/posts`, and `/api/v1/job/posts/{id}` with variant-specific `website-path`.
- Freshippo is another Alibaba-shell site. Reuse the shared Alibaba provider and swap only:
  - `base_url=https://hire.freshippo.com`
  - social channel `hema_group_official_site`
  - campus channel `hema_campus_group_official_site`
- Mihoyo public mobile jobs do not use the login-only `get/id_list` flow. The public seam is:
  - `POST https://ats.openout.mihoyo.com/ats-portal/v1/job/list`
  - `POST https://ats.openout.mihoyo.com/ats-portal/v1/job/info`
  - social routes are hash-based `#/position/{id}`
  - campus routes are hash-based `#/campus/position/{id}`
  - campus vs internship can be split from `jobNatureId` (`1` fulltime, `3` internship, `4` shared).
- In git worktrees with editable installs, prefer running `python -m pytest` from `backend/` so imports resolve to the active worktree instead of another checkout.
- Live smoke may need a repo-local fallback. If the standalone smoke script drifts behind the repo and imports removed modules, call `OfficialAdapter.search_jobs()` directly with `source_companies` and `source_variants` to validate real drafts.

## Notes From 2026-03-12

- Didi dual-source model:
  - Social jobs are available from `GET /recruit-portal-service/api/job/front/list` and `GET /recruit-portal-service/api/job/front/view/{jdId}`.
  - The response shape is `{data, meta}` (no `code` field); do not hardcode status checks.
  - Public social detail URL format is `https://talent.didiglobal.com/social/p/{jdId}`.
  - Campus `Moka` APIs can return encrypted payloads; a reliable fallback is parsing `input#init-data` and extracting `jobs` from preloaded HTML JSON.
- TME split by API family:
  - Experienced: `POST /api/job/list` + `GET /api/job/info`.
  - Campus and internship: `POST /api/uc-job/list` + `GET /api/uc-job/info`.
  - Variant split is stable via `job_type_descr` (`应届生` vs `实习生`).
- Ctrip list/detail contract:
  - Use `POST /api/hrrecruit/getJobAd` for both list and detail.
  - Experienced uses `category=1`; campus pool uses `category=2`.
  - Internship can be split from category 2 via `kindName` (`Summer Intern`) vs `Fresh Graduates`.
  - Detail query uses `condition.fromId=[...]`.
- NetEase dual-domain model:
  - Social and internship use `POST https://hr.163.com/api/hr163/position/queryPage` with `workType=0/1`.
  - Campus uses `GET https://campus.163.com/api/campuspc/position/getJobList`.
  - Resolve campus `projectId` from `GET /api/campuspc/project/navigation/list` instead of hardcoding where possible.
- Baidu SSR data strategy:
  - `window.__INITIAL_DATA__` on `/jobs/social-list` and `/jobs/list?recruitType=...` can provide usable `listDetailData`.
  - Some pages include JS `undefined` in that object; sanitize before `json.loads`.
- Quark as Alibaba-shell reuse:
  - Reuse `AlibabaCareerClient` with Quark channels (`Quark_group_official_site`, `Quark_campus_group_official_site`).
  - Quark search uses `key` instead of `keyword` for query text.

## Reference

Read `references/provider-patterns.md` when the site resembles ByteDance ATSX, Taotian custom JS, Aliyun careers shell, Tencent dual-site (careers + join.qq), PDD shell pages, Feishu, or a Next.js app.
