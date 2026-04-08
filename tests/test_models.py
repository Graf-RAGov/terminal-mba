"""Tests for Pydantic models."""
from __future__ import annotations

from terminalmba.models import Session, Message, SessionDetail


def test_session_creation():
    s = Session(
        id="abc123",
        project="/home/user/proj",
        project_short="proj",
        tool="claude",
        first_message="Hello world",
        messages=5,
        first_ts=1700000000000,
        last_ts=1700000010000,
    )
    assert s.id == "abc123"
    assert s.tool == "claude"
    assert s.messages == 5


def test_message_creation():
    m = Message(role="user", content="Hello")
    assert m.role == "user"
    assert m.content == "Hello"


def test_session_detail_creation():
    detail = SessionDetail(
        messages=[
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello!"),
        ],
    )
    assert len(detail.messages) == 2
    assert detail.messages[0].role == "user"
