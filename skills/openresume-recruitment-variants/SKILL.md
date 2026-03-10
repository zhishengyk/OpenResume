---
name: openresume-recruitment-variants
description: Define and implement recruitment type variants (experienced/campus/internship) for career site adapters. Use when adding new company sources, updating existing extractors, or ensuring variant compliance across the pipeline.
---

# OpenResume Recruitment Variants

This skill defines the standard recruitment type variants that all career site adapters must support.

## Standard Variants

| Variant | Chinese Label | English Label | Target Audience |
|---------|---------------|---------------|-----------------|
| `experienced` | 社招 | Social Recruitment | Experienced professionals |
| `campus` | 校招 | Campus Recruitment | Fresh graduates |
| `internship` | 实习 | Internship | Current students |

## Implementation Checklist

When adding or updating a company adapter, ensure:

### 1. Source Definition (manifest.py)

```python
SOURCES: tuple[CareerSiteSource, ...] = (
    CareerSiteSource(
        key="{company}-experienced",
        company_name="公司名称",
        entry_url="https://...",
        source_site="jobs.company.com",
        collector_key="{company}",
        variant="experienced",
        label="公司社招",
    ),
    CareerSiteSource(
        key="{company}-campus",
        company_name="公司名称",
        entry_url="https://...",
        source_site="jobs.company.com",
        collector_key="{company}",
        variant="campus",
        label="公司校招",
    ),
    CareerSiteSource(
        key="{company}-internship",
        company_name="公司名称",
        entry_url="https://...",
        source_site="jobs.company.com",
        collector_key="{company}",
        variant="internship",
        label="公司实习",
    ),
)
```

### 2. Collector Implementation

The collector must handle all three variants:

```python
VARIANT_CONFIGS = {
    "experienced": VariantConfig(...),
    "campus": VariantConfig(...),
    "internship": VariantConfig(...),
}
```

### 3. API Endpoints

- `GET /api/sources` - Returns all sources with variant field
- `GET /api/source-variants` - Returns available variants list
- `POST /api/search-sessions` - Accepts `source_variants` filter

### 4. Frontend Integration

Frontend already has standard labels in [SearchFilterSidebar.tsx](file:///d:/my%20project/OpenResume/src/components/SearchFilterSidebar.tsx):

```typescript
const VARIANT_LABELS: Record<string, string> = {
  experienced: "社招",
  campus: "校招",
  internship: "实习",
};
```

## Variant Detection Patterns

### URL Patterns

| Variant | Common URL Patterns |
|---------|---------------------|
| experienced | `/experienced`, `/social`, `/society`, `/job` |
| campus | `/campus`, `/grad`, `/graduate`, `/fresh` |
| internship | `/intern`, `/internship`, `/trainee` |

### API Parameters

| Variant | Common Parameters |
|---------|-------------------|
| experienced | `portal_type=2`, `type=social`, `recruitType=1` |
| campus | `portal_type=3`, `type=campus`, `recruitType=2`, `campusType=freshman` |
| internship | `type=intern`, `recruitType=3`, `campusType=internship` |

## Rules

1. Every company source MUST define all three variants if the target site supports them
2. If a site only supports a subset, document the limitation in the source definition
3. Variant values must be lowercase: `experienced`, `campus`, `internship`
4. Source key format: `{company_key}-{variant}`
5. Labels should follow pattern: `{公司名}{类型}` (e.g., "字节跳动社招")

## Reference

Read `references/provider-patterns.md` for provider-specific variant implementations.
