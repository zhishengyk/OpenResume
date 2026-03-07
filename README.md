# OpenResume

OpenResume is a Windows-first desktop application for resume-driven job discovery and user-guided applications. The open source mainline intentionally excludes auto-submit, stealth, captcha bypass, and other anti-detection behavior.

## Stack

- Electron desktop shell
- React + Vite + TypeScript renderer
- FastAPI + SQLModel + SQLite local API service
- Optional Playwright-powered dedicated browser session

## Core product boundaries

- `recommend_only`: search, match, and rank roles
- `review_in_browser`: open the role for manual review
- `guided_apply`: open and pre-stage reusable data, but the final submit is always user-driven

## Development

### Frontend + Electron

```bash
npm install
npm run dev
```

### Backend

```bash
cd backend
pip install -e .[dev]
```

The Electron shell will attempt to boot the backend automatically in development with `python -m openresume_api`.

## Packaging notes

The repository includes the Electron shell and a PyInstaller-friendly backend entrypoint. Producing a production-ready Windows installer still requires:

- installing Python build dependencies
- bundling the backend executable
- wiring the backend executable into Electron Builder resources

Suggested backend bundle step:

```bash
cd backend
pip install -e .[packaging]
pyinstaller --onefile --name openresume-api openresume_api/__main__.py
```

After that:

```bash
npm run package:windows
```
