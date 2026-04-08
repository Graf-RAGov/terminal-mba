# TerminalMBA

## What is this

TerminalMBA is a browser dashboard for managing AI coding agent sessions. Built with FastAPI + Typer + vanilla TypeScript frontend. Supports 6 agents: Claude Code, Claude Extension, Codex CLI, Cursor, OpenCode (SQLite), Kiro CLI (SQLite).

## Project structure

```
src/terminalmba/
  __init__.py         Package init with version
  app.py              FastAPI application + all API routes
  cli.py              Typer CLI (run/list/stats/search/show/handoff/convert/export/import/update/restart/stop)
  data.py             Session loading for all 6 agents, search, cost, active detection
  models.py           Pydantic models (Session, Message, SessionDetail, etc.)
  search.py           Search index with rapidfuzz fuzzy matching
  cost.py             Cost calculation from token usage with MODEL_PRICING
  active.py           Active session detection (PID files + ps scanning)
  terminals.py        Terminal detection, launch, focus
  convert.py          Cross-agent session conversion
  handoff.py          Handoff document generation
  changelog.py        Changelog data
frontend/
  src/
    index.html        HTML template with {{STYLES}} and {{SCRIPT}} placeholders
    app.ts            All frontend TypeScript (Bun build)
    styles.css        CSS with dark/light/monokai themes
    sw.ts             Service worker for PWA
    manifest.json     PWA manifest
    build.ts          Build script: bundles into dist/index.html
tests/
  conftest.py         Shared fixtures
  test_models.py      Model tests
  test_api.py         API endpoint tests
  test_search.py      Search tests
  test_cost.py        Cost calculation tests
```

## Tech stack

- **Backend**: Python 3.12+, FastAPI, Uvicorn, Typer, orjson, rapidfuzz
- **Frontend**: Vanilla TypeScript, Bun (build only), no frameworks
- **Database**: Python sqlite3 module for OpenCode/Kiro (NOT sqlite3 CLI)
- **Tests**: pytest + pytest-asyncio + httpx

## Key conventions

- Use `UV_CACHE_DIR=/tmp/uv-cache` for all uv commands on this system
- Use `asyncio_mode = "auto"` in pyproject.toml
- Use `?` placeholders for SQL queries (never f-strings)
- Template injection uses split/join (avoids $ issues in JS code)
- Project key encoding: `re.sub(r'[^a-zA-Z0-9-]', '-', path)`
- Search index: in-memory, cached 60 seconds
- Timestamps: Claude uses milliseconds, Codex uses seconds

## Running

```bash
# Install deps
UV_CACHE_DIR=/tmp/uv-cache uv sync

# Run server
UV_CACHE_DIR=/tmp/uv-cache uv run terminalmba run

# Run tests
UV_CACHE_DIR=/tmp/uv-cache uv run pytest

# Build frontend
cd frontend && bun install && bun run build
```

## API routes

See src/terminalmba/app.py for full list.
