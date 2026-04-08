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
