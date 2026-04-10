"""Tests for search functionality."""
from __future__ import annotations

from terminalmba.search import search_full_text, fuzzy_search


def test_search_full_text_empty():
    results = search_full_text("hello", [])
    assert results == []


def test_search_short_query():
    results = search_full_text("x", [])
    assert results == []


def test_fuzzy_search_empty():
    results = fuzzy_search("hello", [])
    assert results == []


def test_fuzzy_search_match():
    sessions = [
        {
            "id": "s1",
            "project": "/home/user/myproject",
            "project_short": "myproject",
            "tool": "claude",
            "first_message": "Implement authentication module",
            "messages": 5,
            "first_ts": 1700000000000,
        },
        {
            "id": "s2",
            "project": "/home/user/other",
            "project_short": "other",
            "tool": "codex",
            "first_message": "Fix CSS styling",
            "messages": 3,
            "first_ts": 1700000001000,
        },
    ]

    results = fuzzy_search("authentication", sessions)
    assert len(results) >= 1
    assert any(r["sessionId"] == "s1" for r in results)


def test_fuzzy_search_includes_subagents():
    sessions = [
        {"id": "s1", "project_short": "proj", "tool": "claude", "first_message": "main session", "messages": 5, "first_ts": 1700000000000},
        {"id": "agent-abc123", "project_short": "proj", "tool": "claude", "first_message": "subagent task", "messages": 3, "first_ts": 1700000001000, "_subagent": True},
    ]
    results = fuzzy_search("subagent", sessions, include_subagents=True)
    assert any(r["sessionId"] == "agent-abc123" for r in results)


def test_fuzzy_search_excludes_subagents():
    sessions = [
        {"id": "s1", "project_short": "proj", "tool": "claude", "first_message": "main session", "messages": 5, "first_ts": 1700000000000},
        {"id": "agent-abc123", "project_short": "proj", "tool": "claude", "first_message": "subagent task", "messages": 3, "first_ts": 1700000001000, "_subagent": True},
    ]
    results = fuzzy_search("subagent", sessions, include_subagents=False)
    assert not any(r["sessionId"] == "agent-abc123" for r in results)


def test_fuzzy_search_typo():
    sessions = [
        {
            "id": "s1",
            "project": "/home/user/myproject",
            "project_short": "myproject",
            "tool": "claude",
            "first_message": "Implement authentication",
            "messages": 5,
            "first_ts": 1700000000000,
        },
    ]

    # Typo: "authetication" instead of "authentication"
    results = fuzzy_search("authetication", sessions)
    assert len(results) >= 1
