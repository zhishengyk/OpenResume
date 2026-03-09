# OpenResume

OpenResume is a local desktop job-search workbench built with `Electron + React + FastAPI`.

## Current Branch State

`main` now keeps only the modular platform skeleton:

- `demo`: a local fixture-backed module used for search, matching, review, and safe guided-flow testing
- `liepin`: a placeholder module with capability metadata only

The previous Boss login/search work has been preserved on the local branch:

- `archive/boss-login`

## Design Goal

Each platform belongs to its own module.

- Platform-specific logic stays inside `backend/openresume_api/adapters/<platform>.py`
- Public APIs only depend on capability metadata and a shared adapter contract
- No platform-specific browser/session strategy is hard-coded in the main branch

This keeps the codebase ready for future integrations while keeping the default branch small and low-coupling.

## Development

Install frontend dependencies:

```bash
npm install
```

Install backend dependencies:

```bash
cd backend
python -m pip install -e .[dev]
```

Run the frontend:

```bash
npm run dev:web
```

Run backend tests:

```bash
cd backend
pytest
```

## Notes

- `main` does not contain real Boss login automation anymore
- demo data lives in [`backend/openresume_api/fixtures/demo_jobs.json`](backend/openresume_api/fixtures/demo_jobs.json)
- platform registration lives in [`backend/openresume_api/adapters/registry.py`](backend/openresume_api/adapters/registry.py)
