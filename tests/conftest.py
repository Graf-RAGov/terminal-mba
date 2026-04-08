"""Shared test fixtures for TerminalMBA tests."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_home(tmp_path: Path) -> Path:
    """Create a temporary HOME directory with mock session data."""
    home = tmp_path / "home"
    home.mkdir()

    # Create Claude session directories
    claude_dir = home / ".claude" / "projects" / "-home-testuser-myproject"
    claude_dir.mkdir(parents=True)

    # Create a sample Claude session file
    session_id = "abc123def456"
    session_file = claude_dir / f"{session_id}.jsonl"
    lines = [
        json.dumps({
            "parentUuid": "root",
            "uuid": "msg1",
            "type": "human",
            "message": {"role": "user", "content": [{"type": "text", "text": "Hello, help me write a function"}]},
            "timestamp": "2025-01-15T10:00:00.000Z",
            "sessionId": session_id,
        }),
        json.dumps({
            "parentUuid": "msg1",
            "uuid": "msg2",
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Sure! Here is a function."}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "model": "claude-sonnet-4-20250514",
            },
            "timestamp": "2025-01-15T10:00:05.000Z",
            "sessionId": session_id,
        }),
    ]
    session_file.write_text("\n".join(lines) + "\n")

    return home


@pytest.fixture
def mock_env(tmp_home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set HOME env var to the temporary home directory."""
    monkeypatch.setenv("HOME", str(tmp_home))
    return tmp_home
