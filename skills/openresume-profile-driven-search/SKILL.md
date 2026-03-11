---
name: openresume-profile-driven-search
description: Implement or review OpenResume's profile-driven search flow. Use when Codex needs to wire resume parsing into enriched candidate portraits, keep Search drafts synced without overwriting user edits, extend ranking with tech/project/award evidence, or debug cache invalidation across profile changes.
---

# OpenResume Profile-Driven Search

Use this skill when Search defaults, portrait parsing, ranking, or cache invalidation depend on the saved candidate profile.

## Workflow

1. Confirm the profile contract first: `raw_text`, `tech_stack`, `project_experiences`, and `awards` must exist in backend schema, DB migration, API response, and frontend types.
2. Keep portrait storage simple. Use JSON columns on `candidateprofile`; do not introduce a new subtable or a deep object editor.
3. Treat Search as a draft over the saved profile. First load should initialize from profile, dirty drafts must survive navigation/reload, and profile changes must not overwrite dirty drafts.
4. Keep public search payloads simple. Advanced portrait edits on Search should sync through `PUT /api/profile` before search rather than expanding the search-session API with large nested fields.
5. Invalidate both fetch and LLM caches when portrait-driven search basis changes. Fetch cache should key off effective keyword basis; LLM cache must include a stable `profile_signature`.

## Data Defaults

- `tech_stack`: normalized string array, deduped, capped at 20
- `project_experiences`: small objects with `name`, `role`, `summary`, `technologies`, capped at 6
- `awards`: small objects with `title`, `issuer`, `year`, `summary`, capped at 6
- `raw_text`: persisted resume text for heuristic and LLM enhancement, returned by API but not prominently shown in UI

## Search Draft Rules

- Store Search draft in `localStorage` with `version`, `profileSignature`, `userEdited`, and `fields`.
- If no stored draft exists, initialize from the latest profile.
- If stored draft signature matches, reuse it.
- If signature changed and `userEdited` is false, refresh from profile.
- If signature changed and `userEdited` is true, keep the draft and show a reset notice.
- Reset must rebuild the draft from the latest profile and clear the dirty flag.

## Ranking And Cache Rules

- `job_targets` stay primary for official-source recall; append only 2-3 normalized core tech terms from the profile for keyword expansion.
- Rule matching should add evidence from `tech_stack`, project phrases, and awards, but cap each evidence source so noisy resumes do not dominate ranking.
- `profile_signature` must cover scoring-relevant portrait fields and be reused by:
  - Search draft freshness logic
  - LLM cache keys
  - Any portrait-derived keyword-basis logic

## Review Checklist

- Dirty Search draft is never overwritten by a later profile fetch.
- Search reset uses the latest profile and clears dirty state.
- Old `candidateprofile` rows migrate cleanly with new columns defaulted.
- Fetch cache invalidates when portrait-driven keyword basis changes.
- LLM cache invalidates when portrait evidence changes.
- Search submit syncs advanced portrait edits before creating the session.
- Rule highlights/missing/risk outputs include portrait evidence without becoming spammy.

## Failure Modes

- Profile response includes new fields but frontend types or editors still omit them.
- Search uses portrait-derived tech terms in ranking but not in fetch cache key, causing stale recall.
- LLM cache ignores profile changes and reuses stale explanations.
- Search-page edits modify advanced portrait fields locally but never sync before search.
- Heuristic extraction over-produces noisy project or award phrases; keep normalization conservative.
