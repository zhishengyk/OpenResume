---
name: openresume-official-smoke-test
description: Run live smoke tests for OpenResume official career-site extractors. Use when Codex needs to validate extractor changes against real company URLs, collect per-source stats such as fetch errors, hard-filter drops, detail drops, and final drafts, diagnose zero-result regressions, or confirm that a homepage now yields real jobs before declaring a site adaptation complete.
---

# OpenResume Official Smoke Test

Use this skill after extractor changes or when a real site returns zero jobs.

## Quick Start

Run the smoke script against a source file or repeated sources:

```bash
python C:/Users/admin/Desktop/OpenResume/skills/openresume-official-smoke-test/scripts/run_official_smoke.py --repo C:/Users/admin/Desktop/OpenResume --input-file C:/Users/admin/Desktop/OpenResume/url.md
```

```bash
python C:/Users/admin/Desktop/OpenResume/skills/openresume-official-smoke-test/scripts/run_official_smoke.py --repo C:/Users/admin/Desktop/OpenResume --source "ByteDance=https://jobs.bytedance.com/" --source "Taobao=https://zhaopin.taobao.com/"
```

The script now reuses the backend source classifier so site-specific extractors such as ByteDance, Taobao, and PDD are exercised the same way they are in the real pipeline. Add `--job-target` repeatedly for broader role families and `--detail-limit` to cap detail fetch cost.

## What The Output Means

- `fetch_error`: network, TLS, or site blocking failure before extraction.
- `candidate_count = 0`: wrong extractor hint, missing secondary-page discovery, broken provider auth flow, or bad smoke inputs such as corrupted job targets.
- `hard_filtered = candidate_count`: cards were found, but they are directories, noise pages, or obviously irrelevant roles.
- `detail_dropped > 0` with `final_drafts = 0`: list extraction is partly right, but detail parsing or quality classification is still wrong.
- `final_drafts > 0`: the site is producing usable jobs through the current pipeline.

## Rules

- Run this after code changes and before claiming a site is supported.
- Prefer the smoke script over ad hoc snippets so output stays comparable across runs.
- Use real network targets for acceptance and local fixtures for regression coverage.
- Do not require an LLM key for this smoke path. It exercises the official extraction pipeline directly.
- If the smoke script has drifted behind the repo and imports removed modules, fall back to a repo-local async smoke that calls `OfficialAdapter.search_jobs()` directly with explicit `source_companies` / `source_variants`, then record the returned draft count and top apply URLs.

## Reference

Read `references/diagnostics.md` when the stats need interpretation.
