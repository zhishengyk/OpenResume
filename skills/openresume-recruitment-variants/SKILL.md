---
name: openresume-recruitment-variants
description: Define and implement recruitment type variants (experienced/campus/internship) for career collectors. Use when adding a new company source, extending an existing company with another official endpoint, mapping provider-specific variant parameters, or validating source filtering consistency across backend and frontend.
---

# OpenResume Recruitment Variants

Use this skill to keep variant behavior consistent when adding or modifying official job sources.

## Standard Variants

| Variant | Label (zh-CN) | Target Audience |
|---------|----------------|-----------------|
| `experienced` | `社招` | Experienced professionals |
| `campus` | `校招` | Fresh graduates |
| `internship` | `实习` | Students |

## Implementation Checklist

1. Define three sources per company in `career_collectors/manifest.py` when the site supports them.
2. Keep source key format as `{company_key}-{variant}`.
3. Keep a single `collector_key` per company unless architecture boundaries are truly different.
4. Put provider-specific logic in `career_collectors/providers/`.
5. Put final field mapping to `CollectedJobRecord` in `career_collectors/companies/{company}.py`.
6. Ensure `filter_sources` and runtime summary remain correct after source expansion.

## Small-Change Extension Rule

For repeated work where the change is small:

1. Extend existing skill docs first.
2. Extend existing company collector first.
3. Add one new provider and merge results in the existing collector.
4. Avoid creating a parallel company collector unless required by data ownership or schema.

## Multi-Provider Merge Rules

When one company has multiple official domains:

1. Keep public variant names canonical (`experienced`, `campus`, `internship`).
2. Translate provider-specific params only inside provider classes.
3. Merge and dedupe provider outputs before mapping to `CollectedJobRecord`.
4. Preserve true origin domain in `source_site`.
5. Keep API request/response schemas unchanged unless absolutely necessary.

## Tencent Mapping Template

Use this mapping when adapting Tencent official sources:

| Variant | careers.tencent.com | join.qq.com |
|---------|---------------------|-------------|
| `experienced` | `attrId=1` | not used |
| `campus` | `attrId=2,5` | use `projectMappingIdList` from campus-focused mapping records |
| `internship` | `attrId=3` | use `projectMappingIdList` from internship-focused mapping records |

Recommended pattern:

1. Keep `careers.tencent.com` as baseline provider for all variants.
2. Merge `join.qq.com` into `campus` and `internship`.
3. Deduplicate by stable job id (`PostId`/`postId`) and normalized key.

## Aliyun Mapping Template

Use this mapping when adapting `careers.aliyun.com`:

| Variant | Channel | categoryType |
|---------|---------|--------------|
| `experienced` | `aliyun_group_official_site` | none |
| `campus` | `aliyun_campus_group_official_site` | `freshman` |
| `internship` | `aliyun_campus_group_official_site` | `internship` |

Recommended pattern:

1. Extract `__token__` from HTML and send both `_csrf` query + `x-csrf-token` header.
2. Run `/searchCondition/list` warmup before `/position/search`.
3. Keep one empty-keyword fallback pass when keyword queries return zero.

## Validation Checklist

1. Add provider unit tests for variant mapping, pagination stop, dedupe, encoding fallback.
2. Add collector unit tests for record mapping and source-site behavior.
3. Update manifest/filter tests if source list changes.
4. Run at least:
   - `pytest -q tests/test_career_collectors.py`
   - provider-specific tests
   - related API tests if summary copy or source filters changed

## Reference

Read `../openresume-career-site-adapter/references/provider-patterns.md` for provider-level reverse-engineering patterns.
