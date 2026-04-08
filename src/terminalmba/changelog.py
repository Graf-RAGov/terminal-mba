"""Changelog data."""

CHANGELOG = [
    {
        "version": "0.1.0",
        "date": "2026-04-07",
        "title": "Initial Python reimplementation",
        "changes": [
            "Python backend with FastAPI + Uvicorn",
            "TypeScript frontend with Web Components + Bun",
            "6 agents: Claude Code, Claude Extension, Codex, Cursor, OpenCode, Kiro CLI",
            "Session loading from JSONL and SQLite sources",
            "Full-text search with rapidfuzz fuzzy matching",
            "Cost analytics with per-model pricing",
            "Active session detection via PID files + ps scanning",
            "Session replay with timeline slider",
            "Dark/light/monokai themes via CSS custom properties",
            "PWA support with service worker",
            "Typer CLI with 12 commands",
            "Cross-agent session conversion (Claude <-> Codex)",
            "Session handoff document generation",
        ],
    },
]
