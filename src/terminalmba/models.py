"""Pydantic models for TerminalMBA."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Session(BaseModel):
    id: str
    tool: str = ""  # claude | codex | opencode | cursor | kiro | claude-ext
    project: str = ""
    project_short: str = ""
    first_ts: float = 0
    last_ts: float = 0
    messages: int = 0
    first_message: str = ""
    has_detail: bool = False
    file_size: int = 0
    detail_messages: int = 0
    first_time: str = ""
    last_time: str = ""
    date: str = ""
    git_root: str = ""
    worktree_original_cwd: str = ""


class Message(BaseModel):
    role: str
    content: str
    uuid: str = ""
    model: str = ""
    tokens: dict = Field(default_factory=dict)


class SessionDetail(BaseModel):
    messages: list[Message] = Field(default_factory=list)
    error: str = ""


class ActiveSession(BaseModel):
    pid: int
    sessionId: str = ""
    cwd: str = ""
    startedAt: float = 0
    kind: str = ""
    entrypoint: str = ""
    status: str = ""  # active | waiting
    cpu: float = 0
    memoryMB: int = 0


class Terminal(BaseModel):
    id: str
    name: str
    available: bool


class CostData(BaseModel):
    cost: float = 0
    inputTokens: int = 0
    outputTokens: int = 0
    cacheReadTokens: int = 0
    cacheCreateTokens: int = 0
    contextPctSum: float = 0
    contextTurnCount: int = 0
    model: str = ""


class SearchMatch(BaseModel):
    role: str
    snippet: str


class SearchResult(BaseModel):
    sessionId: str
    matches: list[SearchMatch] = Field(default_factory=list)


class ReplayData(BaseModel):
    messages: list[dict] = Field(default_factory=list)
    startMs: float = 0
    endMs: float = 0
    duration: float = 0


class CostAnalytics(BaseModel):
    totalCost: float = 0
    totalTokens: int = 0
    totalInputTokens: int = 0
    totalOutputTokens: int = 0
    totalCacheReadTokens: int = 0
    totalCacheCreateTokens: int = 0
    avgContextPct: int = 0
    dailyRate: float = 0
    firstDate: str | None = None
    lastDate: str | None = None
    days: int = 1
    totalSessions: int = 0
    byDay: dict = Field(default_factory=dict)
    byWeek: dict = Field(default_factory=dict)
    byProject: dict = Field(default_factory=dict)
    topSessions: list[dict] = Field(default_factory=list)
    byAgent: dict = Field(default_factory=dict)
    agentNoCostData: dict = Field(default_factory=dict)


class HandoffResult(BaseModel):
    ok: bool
    markdown: str = ""
    error: str = ""
    session: dict = Field(default_factory=dict)
    target: str = ""


class ConvertResult(BaseModel):
    ok: bool
    error: str = ""
    source: dict = Field(default_factory=dict)
    target: dict = Field(default_factory=dict)
