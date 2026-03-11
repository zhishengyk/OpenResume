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

## Tencent dual official sites (careers + join.qq)

- Fingerprints:
  - `careers.tencent.com/search.html` with `tencentcareer/api/post/Query`
  - `join.qq.com/post.html?query=p_2` with `api/v1/position/searchPosition`
- Do not assume Tencent has a single source. Use:
  - `careers.tencent.com` as the primary source (all variants)
  - `join.qq.com` as an additional campus/internship source
- `careers.tencent.com` list API:
  - `GET /tencentcareer/api/post/Query`
  - variant attrs:
    - experienced: `attrId=1`
    - campus: `attrId=2,5`
    - internship: `attrId=3`
  - enforce `pageSize <= 50`
  - decode fallback: `utf-8` then `gb18030`
- `join.qq.com` mapping and list APIs:
  - `GET /api/v1/position/getProjectMapping?lang=zh-cn`
  - `POST /api/v1/position/searchPosition`
  - send payload with:
    - `projectMappingIdList`
    - `keyword`, `pageIndex`, `pageSize`
    - empty filters (`bgList`, `workCityList`, `recruitCityList`, `positionFidList`) unless explicitly needed
- Mapping strategy for `projectMappingIdList`:
  - campus: include `recruitType=1` and selected `recruitType=999` non-intern projects
  - internship: include `recruitType=2` and selected `recruitType=999` intern projects
  - do not guess static mapping ids when `getProjectMapping` is available
- Known pitfalls:
  - Chinese keywords on `careers.tencent.com` may under-recall (for example `前端工程师`), so expand with stable English aliases before concluding zero.
  - `projectId` often behaves as legacy/compat field; prefer `projectMappingIdList`.
  - join.qq list payload can be summary-only; keep robust fallback mapping and generate detail URL when `positionUrl` is empty.
  - Merge and dedupe Tencent results across sources by stable job id (`PostId` / `postId`) and source domain.

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

## Recruitment Type Variants (招聘类型变体)

所有网站适配器必须支持三种标准招聘类型变体：

| Variant | 中文标签 | 英文标签 | 说明 |
|---------|----------|----------|------|
| `experienced` | 社招 | Social Recruitment | 面向有工作经验的求职者 |
| `campus` | 校招 | Campus Recruitment | 面向应届毕业生的校园招聘 |
| `internship` | 实习 | Internship | 面向在校学生的实习岗位 |

### 实现要求

1. **Source 定义**：每个公司的数据源必须定义完整的 variant 配置
   ```python
   CareerSiteSource(
       key="company-experienced",  # 格式: {company}-{variant}
       company_name="公司名称",
       entry_url="https://...",
       source_site="jobs.company.com",
       collector_key="company",
       variant="experienced",  # 必须是 experienced/campus/internship 之一
       label="公司社招",
   )
   ```

2. **前端映射**：前端已定义标准标签映射（[SearchFilterSidebar.tsx](file:///d:/my%20project/OpenResume/src/components/SearchFilterSidebar.tsx)）
   ```typescript
   const VARIANT_LABELS: Record<string, string> = {
     experienced: "社招",
     campus: "校招",
     internship: "实习",
   };
   ```

3. **API 端点**：
   - `GET /api/sources` - 返回所有可用数据源，包含 variant 字段
   - `GET /api/source-variants` - 返回可用的招聘类型列表
   - 搜索时通过 `source_variants` 参数过滤

### 各提供商的 Variant 映射

| 提供商 | experienced | campus | internship |
|--------|-------------|--------|------------|
| ByteDance | `/experienced/position` | `/campus/position` | 需要新增 |
| Taobao/Taotian | 社招入口 | `campusType=freshman` | `campusType=internship` |
| PDD | 社招入口 | `/campus/grad` | `/campus/intern` |

## General heuristics

- `candidate_count = 0` usually means the wrong page level, the wrong extractor hint, or a provider-specific token or signature flow that has not been replicated yet.
- A large hard-filter count usually means cards were found, but they are directories, navigation items, or off-target roles.
- A nonzero candidate count followed by detail drops usually means detail classification or provider-specific detail parsing is incomplete.
- When a smoke script says zero on every known-good extractor, verify that the script uses the same source classification logic as `official_sources.py` and that requested job targets are not corrupted.
