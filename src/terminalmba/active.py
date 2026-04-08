"""Active session detection via PID files and ps scanning."""

import os
import re
import subprocess
import sys

import orjson

from .data import CLAUDE_DIR, load_sessions

AGENT_PATTERNS = [
    {"pattern": "claude", "tool": "claude", "match": re.compile(r"\bclaude\b")},
    {"pattern": "codex", "tool": "codex", "match": re.compile(r"\bcodex\b")},
    {"pattern": "opencode", "tool": "opencode", "match": re.compile(r"\bopencode\b")},
    {"pattern": "kiro", "tool": "kiro", "match": re.compile(r"kiro-cli")},
    {"pattern": "cursor-agent", "tool": "cursor", "match": re.compile(r"cursor-agent")},
]


def get_active_sessions() -> list[dict]:
    """Detect running AI agent sessions."""
    active = []
    seen_pids: set[int] = set()

    # 1. Read Claude PID files for session ID mapping
    sessions_dir = os.path.join(CLAUDE_DIR, "sessions")
    claude_pid_map: dict[int, dict] = {}
    if os.path.isdir(sessions_dir):
        for fn in os.listdir(sessions_dir):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(sessions_dir, fn), "r") as f:
                    data = orjson.loads(f.read())
                if data.get("pid"):
                    claude_pid_map[data["pid"]] = data
            except (OSError, orjson.JSONDecodeError):
                pass

    # 2. Scan ALL agent processes via ps
    if sys.platform == "win32":
        return active

    try:
        result = subprocess.run(
            ["bash", "-c",
             'ps aux 2>/dev/null | grep -E "claude|codex|opencode|kiro-cli|cursor-agent" | grep -v grep || true'],
            capture_output=True, text=True, timeout=3
        )
        ps_output = result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return active

    for line in ps_output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 11:
            continue

        try:
            pid = int(parts[1])
        except (ValueError, IndexError):
            continue
        if pid in seen_pids:
            continue

        try:
            cpu = float(parts[2])
        except (ValueError, IndexError):
            cpu = 0
        try:
            rss = int(parts[5])
        except (ValueError, IndexError):
            rss = 0
        stat = parts[7] if len(parts) > 7 else ""
        cmd = " ".join(parts[10:])

        # Determine tool
        tool = ""
        for ap in AGENT_PATTERNS:
            if ap["match"].search(cmd):
                tool = ap["tool"]
                break
        if not tool:
            continue

        # Skip wrappers
        if "node bin/cli" in cmd or "npm" in cmd or "grep" in cmd:
            continue

        seen_pids.add(pid)

        session_id = ""
        cwd = ""
        started_at = 0
        session_source = ""

        if pid in claude_pid_map:
            session_id = claude_pid_map[pid].get("sessionId", "")
            cwd = claude_pid_map[pid].get("cwd", "")
            started_at = claude_pid_map[pid].get("startedAt", 0)
            if session_id:
                session_source = "pid-file"

        # Try lsof for cwd
        if not cwd:
            try:
                lsof_result = subprocess.run(
                    ["lsof", "-d", "cwd", "-p", str(pid), "-Fn"],
                    capture_output=True, text=True, timeout=2
                )
                m = re.search(r"\nn(/[^\n]+)", lsof_result.stdout)
                if m:
                    cwd = m.group(1)
            except (subprocess.TimeoutExpired, OSError):
                pass

        # Try matching by cwd
        if not session_id:
            all_sessions = load_sessions()
            match = next((s for s in all_sessions if s.get("tool") == tool and s.get("project") == cwd), None)
            if match:
                session_id = match["id"]
                session_source = "cwd-match"
            else:
                latest = next(
                    (s for s in sorted(
                        (s for s in all_sessions if s.get("tool") == tool),
                        key=lambda x: x.get("last_ts", 0), reverse=True
                    )),
                    None
                )
                if latest:
                    session_id = latest["id"]
                    session_source = "fallback-latest"

        status = "waiting" if cpu < 1 and ("S" in stat or "T" in stat) else "active"

        active.append({
            "pid": pid,
            "sessionId": session_id,
            "cwd": cwd,
            "startedAt": started_at,
            "kind": tool,
            "entrypoint": tool,
            "status": status,
            "cpu": cpu,
            "memoryMB": round(rss / 1024),
            "_sessionSource": session_source,
        })

    return active
