# OpenResume

OpenResume is a local desktop job-search workbench built with `Electron + React + FastAPI`.

## Current Branch State

`main` now exposes only two platform entries:

- `official`: connected and selectable; searches official career sites from `url.md`
- `boss`: visible but disabled; Boss work stays parked on `archive/boss-login`

The search pipeline is now:

1. Parse official site sources from `url.md`
2. Fetch official pages
3. Clean and normalize job candidates in code
4. Rank cleaned jobs with an OpenAI-compatible model, or explicit heuristic fallback
5. Launch in-app verification popups for guided apply when login/captcha is required

## Key Behaviors

- Platform selection is multi-select on the frontend
- Disabled platforms remain visible but cannot be checked
- Search sessions store `requested_platforms`
- Guided apply uses the uploaded local resume and opens verification inside the app popup
- If model configuration is missing or model calls fail, the UI shows that results are using heuristic fallback

## Model Configuration

Set these environment variables to enable OpenAI-compatible ranking:

```bash
OPENRESUME_LLM_PROVIDER=openai_compatible
OPENRESUME_OPENAI_BASE_URL=https://your-model-endpoint/v1
OPENRESUME_OPENAI_API_KEY=your-key
OPENRESUME_OPENAI_MODEL=your-model-name
```

Without these values, the backend falls back to heuristic ranking and returns an explicit degraded-analysis notice to the UI.

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

Run the desktop app in development:

```bash
npm run dev
```

Run backend tests:

```bash
cd backend
pytest
```

Run frontend type checking:

```bash
npm run typecheck
```
