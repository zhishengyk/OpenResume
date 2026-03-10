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
- PDD shell pages: follow `/campus/grad` and `/campus/intern` before concluding the page is empty. The real jobs live behind JSON APIs, not the first HTML response.
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

## Reference

Read `references/provider-patterns.md` when the site resembles ByteDance ATSX, Taotian custom JS, Tencent dual-site (careers + join.qq), PDD shell pages, Feishu, or a Next.js app.
