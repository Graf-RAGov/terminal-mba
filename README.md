# TerminalMBA (Python fork of codedash)

A fork of [codedash](https://github.com/vakovalskii/codedash) by [@vakovalskii](https://github.com/vakovalskii), rewritten from scratch in a single Claude Code session.

The goal: get rid of Node.js and rewrite everything possible from Node to Python + uv. Everything up to the initial commit is a one-shot vibe code; after that, the project lives on its own.

Browser dashboard for managing AI coding agent sessions. Built with FastAPI + Typer + vanilla TypeScript frontend. Supports 6 agents: Claude Code, Claude Extension, Codex CLI, Cursor, OpenCode (SQLite), Kiro CLI (SQLite).

## Quick start

The easiest way to run this project is to ask any AI coding agent (Claude Code, Codex, Cursor, etc.) to do it for you:

> Clone https://github.com/Graf-RAGov/terminal-mba, install dependencies, build the frontend, and run the server

The agent will figure out what to install, build, and run — and give you a URL to open in your browser.

## What changed from the original

- **Language**: Node.js → Python 3.12+ (FastAPI + Typer + uv)
- **Frontend**: Plain JS → vanilla TypeScript (Bun build only, no Node runtime)
- **Search**: rapidfuzz for fuzzy matching
- **SQLite**: Native `sqlite3` module instead of CLI

## Install

```bash
pip install terminalmba
```

## Usage

```bash
terminalmba run          # Start dashboard server
terminalmba list         # List sessions in terminal
terminalmba stats        # Show session statistics
terminalmba search QUERY # Search across all sessions
terminalmba show ID      # Show session details
terminalmba handoff ID   # Generate handoff document
terminalmba convert ID   # Convert session between agents
terminalmba export       # Export all sessions
terminalmba import FILE  # Import sessions from archive
terminalmba update       # Check for updates
terminalmba stop         # Stop the server
```

## Prerequisites

- **Python 3.12+** — [python.org](https://www.python.org/downloads/)
- **[uv](https://docs.astral.sh/uv/)** — Python package/project manager
- **[Bun](https://bun.sh/)** — JS bundler (only needed for frontend builds)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Bun
curl -fsSL https://bun.sh/install | bash
```

## Development

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

## Remote session sync

Pull sessions from other Macs on your local network into your dashboard.

**1. Enable SSH on the remote Mac**

System Settings → General → Sharing → Remote Login → On

**2. Add the remote machine**

```bash
terminalmba remote add user@192.168.1.100
```

This sets up SSH key authentication automatically. You can find the remote Mac's IP with `ipconfig getifaddr en0`.

**3. Sync sessions**

```bash
terminalmba remote sync
```

## Tech stack

- **FastAPI** + **Uvicorn** — API
- **Typer** — CLI
- **orjson** — JSON parsing
- **rapidfuzz** — fuzzy search
- **Vanilla TypeScript** + **Web Components** — frontend
- **Bun** — bundler / dev server / PM
- **Hand-written `sw.ts` + `manifest.json`** — PWA
- **Vanilla CSS** custom properties — styling
- **Playwright** — E2E testing
- **pytest** + **httpx** — unit/API tests
