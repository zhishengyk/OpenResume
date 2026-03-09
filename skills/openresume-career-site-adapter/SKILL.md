---
name: openresume-career-site-adapter
description: Adapt official recruitment and career homepages into reliable job extraction flows in OpenResume. Use when Codex needs to reverse-engineer a company careers site, decide whether the supplied URL is only an entry page, discover secondary listing or detail links, identify provider fingerprints such as Feishu, Moka, Hotjob, JSON SSR, or Next.js shells, patch the right extractor under backend/openresume_api/adapters/official_extractors/, or explain why a live site returns zero usable jobs.
---

# OpenResume Career Site Adapter

Use this skill to turn a company career homepage into real job detail extraction without weakening the existing quality gates.

## Workflow

1. Reproduce the failure on the exact homepage the user supplied. Treat that URL as an entry page, not proof that it is the real job list.
2. Fingerprint the provider before editing code. Inspect redirects, script ids, embedded JSON, JS bundle names, and obvious route fragments.
3. Discover the next hop. Many sites hide jobs behind category pages, referral pages, share pages, tabs, or APIs that are not linked as direct detail pages.
4. Patch the narrowest layer that fits the problem. Put provider-specific parsing in the extractor, shared cleanup in `common.py`, and multi-page orchestration in `official.py`.
5. Add a fixture for the newly discovered payload or page shape, then rerun live smoke plus pytest.

## Provider Checkpoints

- ByteDance ATSX: prioritize the canonical `/campus/position` list page over noisy share or keyword pages, then use the signed campus APIs for real list and detail payloads.
- Taobao or Taotian: treat `zhaopin.taobao.com` as an entry only. Move to `talent.taotian.com/campus/position-list`, obtain the page token, then call the real search endpoints.
- PDD shell pages: follow `/campus/grad` and `/campus/intern` before concluding the page is empty. The real jobs live behind JSON APIs, not the first HTML response.

## Where To Patch

- `backend/openresume_api/adapters/official.py`
  Use for source-page preparation, secondary-page follow-up, list/detail dedupe, and quality gating orchestration.
- `backend/openresume_api/adapters/official_extractors/feishu.py`
  Use for Feishu or ATSX pages, including `js-websiteInfo`, referral pages, and secondary position routes.
- `backend/openresume_api/adapters/official_extractors/json_ssr.py`
  Use for `__NEXT_DATA__`, `__NUXT__`, `application/json`, and SSR payloads.
- `backend/openresume_api/adapters/official_extractors/generic.py`
  Use only when the site truly exposes jobs in ordinary DOM links or cards.
- `backend/openresume_api/adapters/official_extractors/common.py`
  Use for title cleanup, city normalization, salary parsing, directory classification, and quality scoring.

## Rules

- Start from the homepage and assume it may only contain links to the real search pages.
- Prefer structured payloads over brittle DOM scraping when both exist.
- Follow redirects and short links. Some providers expose jobs only through share or referral URLs.
- Search JS bundles for `api/`, router paths, and query builders when the HTML is just a shell.
- If a homepage links into a filtered share page, try the canonical unfiltered list page as well before accepting a zero-result API response.
- Do not relax hard filters to make a site look green. If everything is filtered as directory or noise, extraction is still wrong.
- Keep `raw_payload.quality` truthful so matching logic keeps working.

## Reference

Read `references/provider-patterns.md` when the site resembles ByteDance ATSX, Taotian custom JS, PDD shell pages, Feishu, or a Next.js app.
