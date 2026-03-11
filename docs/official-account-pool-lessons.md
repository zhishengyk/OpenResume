# Official Account Pool Lessons

## Scope

This iteration delivered two linked changes:

1. Meituan official collector performance optimization.
2. Official account pool, resume asset pool, and batch apply architecture for five companies:
   `bytedance`, `tencent`, `meituan`, `pdd`, `aliyun`.

The design target was not "full autopilot at all costs". The target was a stable local-control system:

- default to `semi_auto`
- support `auto_submit` only with explicit confirmation
- persist reusable account and resume assets
- keep manual verification and risk boundaries visible in the UI

## What Worked

### 1. Fixing the biggest bottleneck first was correct

Meituan was the dominant latency outlier, so Phase 1 focused on:

- honoring source limit early
- parallelizing list pagination after page 1
- reusing clients for detail fetch
- batching detail fetch with bounded workers

This reduced the Meituan bottleneck from the previous triple-digit-second range to a workable level and improved the total official-source search path without perturbing already-fast providers.

### 2. Asset pooling should be modeled as separate infrastructure

Keeping search portrait and apply assets separate avoided overloading `CandidateProfile`.

- `CandidateProfile` still represents search/ranking portrait data.
- `ResumeAsset` represents files used for apply execution.
- `CompanyBinding` ties a company to its default resume asset.
- `OfficialAccount` and `OfficialSessionCache` separate credentials metadata from browser session state.

This split made the UI and backend rules cleaner:

- changing search portrait does not silently change apply assets
- changing company default resume does not mutate ranking context
- session cache lifecycle can evolve without touching candidate portrait

### 3. Batch apply needs its own state model

Adding `ApplyBatch` and `ApplyBatchItem` was the right abstraction.

Why:

- batch-level status is needed for queue/history UX
- item-level status is needed for verification blockers and mixed outcomes
- single global worker in v1 is simpler and safer than pretending concurrency is free

The main state transitions are:

- `queued`
- `running`
- `needs_verification`
- `prepared`
- `submitted`
- `failed`
- `cancelled`

This is enough for semi-auto and auto-submit without inventing a fake "success" state that hides where the browser actually stopped.

## Key Design Decisions

### Credentials storage

Passwords are stored in OS keyring when available, with JSON fallback only when keyring is unavailable.

Reason:

- DB should not hold sensitive secrets
- local desktop app should still function when keyring integration is missing

### Session cache storage

Per-account browser storage state is persisted on disk under a company/account-scoped path.

Reason:

- multiple accounts per company are expected
- cache invalidation and inspection need a deterministic location
- browser state belongs to the account, not the search session

### Execution modes

Two modes are intentionally exposed:

- `semi_auto`: stop before final submit
- `auto_submit`: continue only when the page structure is recognized and risk is explicitly confirmed

Reason:

- most breakages and policy risk happen near login, captcha, and final submit
- users need a strong default safety rail
- fully automatic apply is useful, but should never be the default path

## Frontend Lessons

### 1. Account pool belongs in primary navigation

Putting account/resume management in left navigation worked better than hiding it in search filters.

Reason:

- it is a persistent asset-management workflow, not a per-search option
- users need to revisit it before and after searches
- batch apply depends on it globally

### 2. Results page should stay job-centric

The batch UX added only three things to the results page:

- selection
- execution mode switch
- create batch action

Everything else stayed job-focused. This kept the page understandable and prevented the search experience from collapsing into an operations dashboard.

### 3. History must show both attempts and batches

Single guided attempts and batch executions solve different problems:

- attempts are useful for manual one-off flows
- batches are the real source of truth for pooled-account automation

Keeping both views avoided breaking existing user habits while exposing the new architecture.

## Failures and Fixes During Implementation

### Detached ORM instances in background batch worker

Problem:

- background execution held onto ORM instances across session boundaries

Fix:

- capture primitive IDs before leaving the session
- re-hydrate objects in a fresh session for subsequent operations

Lesson:

- async/background services should pass identifiers, not live ORM objects

### Test DB reset instability

Problem:

- `drop_all/create_all` against the SQLite test file was unreliable with the current startup lifecycle

Fix:

- dispose the test engine
- delete the sqlite file directly
- recreate schema cleanly

Lesson:

- for local SQLite tests, file recreation is often more reliable than repeated schema mutation

## Current Limitations

- Drivers are intentionally generic and selector-based; they are a v1 compatibility layer, not deep company-specific automation.
- Batch execution is globally serialized in v1.
- `guided_apply` compatibility is still preserved as a standalone path; batch apply is the primary architecture for pooled execution.
- Captcha/manual verification still requires human completion.
- Resume asset binding is company-default only; there is not yet per-batch override UI.

## Recommended Next Steps

1. Add company-specific driver refinements where generic selectors are insufficient.
2. Add per-batch override for account and resume selection before launch.
3. Add richer session-cache health checks and expiry heuristics.
4. Add audit logging around auto-submit decisions and selector matches.
5. Expand official-site coverage beyond the first five companies only after driver stability is proven.

## Rules Worth Keeping

- Optimize the slowest source before broad refactors.
- Keep search portrait and apply assets separate.
- Default to semi-auto.
- Make verification blockers explicit in both backend state and frontend UI.
- Model batch state as a first-class concept instead of inferring it from logs.
