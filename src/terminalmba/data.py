"""Session loading for all 6 agents: Claude, Claude Extension, Codex, Cursor, OpenCode, Kiro."""

import os
import re
import time
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import orjson

# ── Constants ──────────────────────────────────────────────

HOME = str(Path.home())
CLAUDE_DIR = os.path.join(HOME, ".claude")
CODEX_DIR = os.path.join(HOME, ".codex")
OPENCODE_DB = os.path.join(HOME, ".local", "share", "opencode", "opencode.db")
KIRO_DB = os.path.join(HOME, "Library", "Application Support", "kiro-cli", "data.sqlite3")
CURSOR_DIR = os.path.join(HOME, ".cursor")
CURSOR_PROJECTS = os.path.join(CURSOR_DIR, "projects")
CURSOR_CHATS = os.path.join(CURSOR_DIR, "chats")
HISTORY_FILE = os.path.join(CLAUDE_DIR, "history.jsonl")
PROJECTS_DIR = os.path.join(CLAUDE_DIR, "projects")


# ── Helpers ────────────────────────────────────────────────

def read_lines(file_path: str) -> list[str]:
    """Read file lines, handling \\r\\n (Windows/WSL)."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\r\n") for line in f if line.strip()]
    except (OSError, IOError):
        return []


def extract_content(raw) -> str:
    """Extract text content from message content field."""
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for b in raw:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                parts.append(b.get("text", "") or b.get("input_text", ""))
        return "\n".join(p for p in parts if p)
    return str(raw)


def is_system_message(text: str) -> bool:
    """Check if message is a system/meta message that should be filtered."""
    if not text:
        return True
    t = text.strip()
    if t in ("exit", "quit", "/exit"):
        return True
    if t.startswith("<permissions"):
        return True
    if t.startswith("<environment_context"):
        return True
    if t.startswith("<collaboration_mode"):
        return True
    if t.startswith("# AGENTS.md"):
        return True
    if t.startswith("<INSTRUCTIONS>"):
        return True
    if t.startswith("You are Codex"):
        return True
    if t.startswith("Filesystem sandboxing"):
        return True
    return False


def _parse_json_line(line: str):
    """Parse a single JSON line, returns None on failure."""
    try:
        return orjson.loads(line)
    except (orjson.JSONDecodeError, ValueError):
        return None


# ── Claude Session Parsing ─────────────────────────────────

def parse_claude_session_file(session_file: str) -> dict | None:
    """Parse a Claude JSONL session file and return summary info."""
    if not os.path.exists(session_file):
        return None
    try:
        stat = os.stat(session_file)
        lines = read_lines(session_file)
    except OSError:
        return None

    project_path = ""
    tool = "claude"
    msg_count = 0
    first_msg = ""
    custom_title = ""
    first_ts = stat.st_mtime * 1000
    last_ts = stat.st_mtime * 1000
    entrypoint_found = False
    worktree_original_cwd = ""

    for line in lines:
        entry = _parse_json_line(line)
        if entry is None:
            continue
        entry_type = entry.get("type", "")
        if entry_type in ("user", "assistant"):
            msg_count += 1
        ts = entry.get("timestamp")
        if ts is not None:
            if isinstance(ts, (int, float)):
                if ts < first_ts:
                    first_ts = ts
                if ts > last_ts:
                    last_ts = ts
            elif isinstance(ts, str):
                try:
                    parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000
                    if parsed_ts < first_ts:
                        first_ts = parsed_ts
                    if parsed_ts > last_ts:
                        last_ts = parsed_ts
                except (ValueError, TypeError):
                    pass

        if not project_path and entry_type == "user" and entry.get("cwd"):
            project_path = entry["cwd"]

        if (not worktree_original_cwd and entry_type == "worktree-state"
                and entry.get("worktreeSession", {}).get("originalCwd")):
            worktree_original_cwd = entry["worktreeSession"]["originalCwd"]

        if not entrypoint_found and entry_type == "user" and entry.get("entrypoint"):
            entrypoint_found = True
            if entry["entrypoint"] != "cli":
                tool = "claude-ext"

        if entry_type == "custom-title" and isinstance(entry.get("customTitle"), str):
            title = entry["customTitle"].strip()
            if title:
                custom_title = title[:200]

        if not first_msg and entry_type == "user":
            msg = entry.get("message", {})
            if msg:
                content = extract_content(msg.get("content", "")).strip()
                if content:
                    first_msg = content[:200]

    return {
        "projectPath": project_path,
        "tool": tool,
        "msgCount": msg_count,
        "firstMsg": first_msg,
        "customTitle": custom_title,
        "firstTs": first_ts,
        "lastTs": last_ts,
        "fileSize": stat.st_size,
        "worktreeOriginalCwd": worktree_original_cwd,
    }


def merge_claude_session_detail(session: dict, summary: dict, session_file: str) -> None:
    """Enrich a session dict with detail from parsed session file."""
    if not session or not summary:
        return
    session["tool"] = summary.get("tool", session.get("tool", ""))
    session["has_detail"] = True
    session["file_size"] = summary.get("fileSize", 0)
    session["detail_messages"] = summary.get("msgCount", 0)
    session["_session_file"] = session_file

    if not session.get("project") and summary.get("projectPath"):
        session["project"] = summary["projectPath"]
        session["project_short"] = summary["projectPath"].replace(HOME, "~")

    if summary.get("worktreeOriginalCwd"):
        session["worktree_original_cwd"] = summary["worktreeOriginalCwd"]

    if summary.get("customTitle"):
        session["first_message"] = summary["customTitle"]


# ── Codex Session Parsing ──────────────────────────────────

def parse_codex_session_index(codex_dir: str) -> dict[str, str]:
    """Parse session_index.jsonl for Codex session titles."""
    titles: dict[str, str] = {}
    title_meta: dict[str, dict] = {}
    index_file = os.path.join(codex_dir, "session_index.jsonl")
    if not os.path.exists(index_file):
        return titles

    lines = read_lines(index_file)
    for line in lines:
        entry = _parse_json_line(line)
        if entry is None:
            continue
        sid = entry.get("id") or entry.get("session_id") or entry.get("sessionId")
        if not sid or not isinstance(entry.get("thread_name"), str):
            continue
        title = entry["thread_name"].strip()
        if not title:
            continue

        updated_at_val = entry.get("updated_at")
        updated_at = _parse_timestamp_value(updated_at_val)
        has_updated_at = updated_at is not None

        existing = title_meta.get(sid)
        if not existing:
            titles[sid] = title[:200]
            title_meta[sid] = {"updatedAt": updated_at, "hasUpdatedAt": has_updated_at}
            continue

        if ((has_updated_at and not existing["hasUpdatedAt"])
                or (has_updated_at and existing["hasUpdatedAt"]
                    and updated_at >= existing["updatedAt"])
                or (not has_updated_at and not existing["hasUpdatedAt"])):
            titles[sid] = title[:200]
            title_meta[sid] = {"updatedAt": updated_at, "hasUpdatedAt": has_updated_at}

    return titles


def _parse_timestamp_value(value) -> float | None:
    """Parse a timestamp value (number or string) to milliseconds."""
    if isinstance(value, (int, float)) and value == value:  # not NaN
        return float(value)
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        if trimmed.isdigit():
            return float(trimmed)
        try:
            return datetime.fromisoformat(trimmed.replace("Z", "+00:00")).timestamp() * 1000
        except (ValueError, TypeError):
            return None
    return None


def parse_codex_session_file(session_file: str) -> dict | None:
    """Parse a Codex JSONL session file and return summary info."""
    if not os.path.exists(session_file):
        return None
    try:
        stat = os.stat(session_file)
        lines = read_lines(session_file)
    except OSError:
        return None

    project_path = ""
    msg_count = 0
    first_msg = ""
    first_ts = stat.st_mtime * 1000
    last_ts = stat.st_mtime * 1000

    for line in lines:
        entry = _parse_json_line(line)
        if entry is None:
            continue

        ts_val = entry.get("timestamp") or entry.get("ts")
        ts = _parse_timestamp_value(ts_val)
        if ts is not None:
            if ts < first_ts:
                first_ts = ts
            if ts > last_ts:
                last_ts = ts

        if entry.get("type") == "session_meta" and entry.get("payload", {}).get("cwd") and not project_path:
            project_path = entry["payload"]["cwd"]
            continue

        if entry.get("type") != "response_item" or not entry.get("payload"):
            continue
        role = entry["payload"].get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = extract_content(entry["payload"].get("content"))
        if not content or is_system_message(content):
            continue
        msg_count += 1
        if not first_msg:
            first_msg = content[:200]

    return {
        "projectPath": project_path,
        "msgCount": msg_count,
        "firstMsg": first_msg,
        "firstTs": first_ts,
        "lastTs": last_ts,
        "fileSize": stat.st_size,
    }


def scan_codex_sessions() -> list[dict]:
    """Scan all Codex sessions from history and session files."""
    sessions = []
    codex_titles = parse_codex_session_index(CODEX_DIR)
    codex_history = os.path.join(CODEX_DIR, "history.jsonl")

    if os.path.exists(codex_history):
        lines = read_lines(codex_history)
        seen_ids = set()
        for line in lines:
            d = _parse_json_line(line)
            if d is None:
                continue
            sid = d.get("session_id") or d.get("sessionId") or d.get("id")
            if not sid or sid in seen_ids:
                continue
            seen_ids.add(sid)
            ts = d.get("ts", 0)
            if ts:
                ts = ts * 1000  # Codex uses seconds
            else:
                ts = d.get("timestamp", time.time() * 1000)

            sessions.append({
                "id": sid,
                "tool": "codex",
                "project": d.get("project", "") or d.get("cwd", ""),
                "project_short": (d.get("project", "") or d.get("cwd", "")).replace(HOME, "~"),
                "first_ts": ts,
                "last_ts": ts,
                "messages": 1,
                "first_message": codex_titles.get(sid, "") or d.get("text", "") or d.get("display", "") or d.get("prompt", ""),
                "has_detail": False,
                "file_size": 0,
                "detail_messages": 0,
            })

    # Enrich with session files
    codex_sessions_dir = os.path.join(CODEX_DIR, "sessions")
    if os.path.isdir(codex_sessions_dir):
        try:
            files = []
            for root, _, filenames in os.walk(codex_sessions_dir):
                for fn in filenames:
                    if fn.endswith(".jsonl"):
                        files.append(os.path.join(root, fn))

            uuid_pattern = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
            for f in files:
                basename = os.path.splitext(os.path.basename(f))[0]
                m = uuid_pattern.search(basename)
                if not m:
                    continue
                sid = m.group(1)
                summary = parse_codex_session_file(f)
                if not summary:
                    continue

                existing = next((s for s in sessions if s["id"] == sid), None)
                if existing:
                    existing["has_detail"] = True
                    existing["file_size"] = summary["fileSize"]
                    existing["messages"] = summary["msgCount"]
                    existing["detail_messages"] = summary["msgCount"]
                    if codex_titles.get(sid):
                        existing["first_message"] = codex_titles[sid]
                    elif summary["firstMsg"] and not existing["first_message"]:
                        existing["first_message"] = summary["firstMsg"]
                    if summary["projectPath"] and not existing["project"]:
                        existing["project"] = summary["projectPath"]
                        existing["project_short"] = summary["projectPath"].replace(HOME, "~")
                    existing["first_ts"] = min(existing["first_ts"], summary["firstTs"])
                    existing["last_ts"] = max(existing["last_ts"], summary["lastTs"])
                else:
                    sessions.append({
                        "id": sid,
                        "tool": "codex",
                        "project": summary["projectPath"],
                        "project_short": summary["projectPath"].replace(HOME, "~") if summary["projectPath"] else "",
                        "first_ts": summary["firstTs"],
                        "last_ts": summary["lastTs"],
                        "messages": summary["msgCount"],
                        "first_message": codex_titles.get(sid, "") or summary["firstMsg"] or "",
                        "has_detail": True,
                        "file_size": summary["fileSize"],
                        "detail_messages": summary["msgCount"],
                    })
        except OSError:
            pass

    return sessions


# ── OpenCode Session Loading (SQLite) ──────────────────────

def scan_opencode_sessions() -> list[dict]:
    """Scan OpenCode sessions from SQLite database."""
    sessions = []
    if not os.path.exists(OPENCODE_DB):
        return sessions
    try:
        conn = sqlite3.connect(OPENCODE_DB)
        cursor = conn.execute(
            "SELECT s.id, s.title, s.directory, s.time_created, s.time_updated, COUNT(m.id) as msg_count "
            "FROM session s LEFT JOIN message m ON m.session_id = s.id "
            "GROUP BY s.id ORDER BY s.time_updated DESC"
        )
        for row in cursor:
            sid, title, directory, time_created, time_updated, msg_count = row
            sessions.append({
                "id": sid,
                "tool": "opencode",
                "project": directory or "",
                "project_short": (directory or "").replace(HOME, "~"),
                "first_ts": int(time_created or 0) or int(time.time() * 1000),
                "last_ts": int(time_updated or 0) or int(time.time() * 1000),
                "messages": msg_count or 0,
                "first_message": title or "",
                "has_detail": True,
                "file_size": 0,
                "detail_messages": msg_count or 0,
            })
        conn.close()
    except (sqlite3.Error, OSError):
        pass
    return sessions


def load_opencode_detail(session_id: str) -> dict:
    """Load OpenCode session messages from SQLite."""
    if not os.path.exists(OPENCODE_DB):
        return {"messages": []}
    try:
        conn = sqlite3.connect(OPENCODE_DB)
        cursor = conn.execute(
            "SELECT m.data, GROUP_CONCAT(p.data, '|||') "
            "FROM message m LEFT JOIN part p ON p.message_id = m.id "
            "WHERE m.session_id = ? "
            "GROUP BY m.id ORDER BY m.time_created",
            (session_id,)
        )
        messages = []
        for row in cursor:
            msg_json_str, parts_raw = row
            if not msg_json_str:
                continue
            try:
                msg_data = orjson.loads(msg_json_str)
            except (orjson.JSONDecodeError, ValueError):
                continue
            role = msg_data.get("role", "")
            if role not in ("user", "assistant"):
                continue
            content = ""
            if parts_raw:
                for part_str in parts_raw.split("|||"):
                    try:
                        part = orjson.loads(part_str)
                        if part.get("type") == "text" and part.get("text"):
                            content += part["text"] + "\n"
                    except (orjson.JSONDecodeError, ValueError):
                        pass
            content = content.strip()
            if not content:
                continue
            messages.append({
                "role": role,
                "content": content[:2000],
                "uuid": "",
                "model": msg_data.get("modelID", "") or (msg_data.get("model", {}) or {}).get("modelID", ""),
                "tokens": msg_data.get("tokens", {}),
            })
        conn.close()
        return {"messages": messages[:200]}
    except (sqlite3.Error, OSError):
        return {"messages": []}


# ── Kiro Session Loading (SQLite) ──────────────────────────

def scan_kiro_sessions() -> list[dict]:
    """Scan Kiro sessions from SQLite database."""
    sessions = []
    if not os.path.exists(KIRO_DB):
        return sessions
    try:
        conn = sqlite3.connect(KIRO_DB)
        cursor = conn.execute(
            "SELECT key, conversation_id, created_at, updated_at, substr(value, 1, 500), length(value) "
            "FROM conversations_v2 ORDER BY updated_at DESC"
        )
        for row in cursor:
            directory, conv_id, created_at, updated_at, value_peek, value_len = row
            first_msg = ""
            msg_count = 0
            if value_peek:
                import re as _re
                prompt_match = _re.search(r'"prompt":"([^"]{1,100})"', value_peek)
                if prompt_match:
                    first_msg = prompt_match.group(1)
                prompt_count = value_peek.count('"prompt"')
                msg_count = prompt_count * 2
                if msg_count == 0 and (value_len or 0) > 100:
                    msg_count = max(2, (value_len or 0) // 2000)

            sessions.append({
                "id": conv_id,
                "tool": "kiro",
                "project": directory or "",
                "project_short": (directory or "").replace(HOME, "~"),
                "first_ts": int(created_at or 0) or int(time.time() * 1000),
                "last_ts": int(updated_at or 0) or int(time.time() * 1000),
                "messages": msg_count,
                "first_message": first_msg,
                "has_detail": True,
                "file_size": value_len or 0,
                "detail_messages": msg_count,
            })
        conn.close()
    except (sqlite3.Error, OSError):
        pass
    return sessions


def load_kiro_detail(conversation_id: str) -> dict:
    """Load Kiro session messages from SQLite."""
    if not os.path.exists(KIRO_DB):
        return {"messages": []}
    try:
        conn = sqlite3.connect(KIRO_DB)
        cursor = conn.execute(
            "SELECT value FROM conversations_v2 WHERE conversation_id = ?",
            (conversation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row or not row[0]:
            return {"messages": []}

        data = orjson.loads(row[0])
        messages = []
        for entry in data.get("history", []):
            if entry.get("user"):
                prompt = (entry["user"].get("content", {}) or {}).get("Prompt", {}) or {}
                text = prompt.get("prompt", "")
                if text:
                    messages.append({"role": "user", "content": text[:2000], "uuid": ""})
            if entry.get("assistant"):
                resp = entry["assistant"].get("Response", {}) or entry["assistant"].get("response", {}) or {}
                text = resp.get("content", "")
                if text:
                    messages.append({"role": "assistant", "content": text[:2000], "uuid": resp.get("message_id", "")})

        return {"messages": messages[:200]}
    except (sqlite3.Error, OSError, orjson.JSONDecodeError):
        return {"messages": []}


# ── Cursor Session Loading ─────────────────────────────────

def decode_cursor_project_folder_key(proj: str) -> str:
    """Decode Cursor project folder key to actual path."""
    if not proj:
        return ""
    enc = proj
    cwd = ""
    while enc:
        parent = cwd or "/"
        try:
            dirs = sorted(
                [e.name for e in os.scandir(parent) if e.is_dir()],
                key=len,
                reverse=True,
            )
        except OSError:
            return cwd or ("/" + proj.replace("-", "/"))

        matched = None
        for d in dirs:
            encoded = re.sub(r"[^a-zA-Z0-9-]", "-", d)
            if enc == encoded or (enc.startswith(encoded) and (len(enc) == len(encoded) or enc[len(encoded)] == "-")):
                matched = d
                break

        if not matched:
            idx = enc.find("-")
            part = enc if idx == -1 else enc[:idx]
            nxt = os.path.join(cwd, part) if cwd else os.path.join("/", part)
            if os.path.exists(nxt):
                cwd = nxt
                enc = "" if idx == -1 else enc[idx + 1:]
            else:
                return cwd or ("/" + proj.replace("-", "/"))
            continue

        cwd = os.path.join(cwd, matched) if cwd else os.path.join("/", matched)
        enc = "" if len(enc) == len(matched) else enc[len(matched) + 1:]

    return cwd


def scan_cursor_sessions() -> list[dict]:
    """Scan Cursor sessions from projects and chats directories."""
    sessions = []

    # Scan ~/.cursor/projects/*/agent-transcripts/*/*.jsonl
    if os.path.isdir(CURSOR_PROJECTS):
        try:
            for proj in os.listdir(CURSOR_PROJECTS):
                transcripts_dir = os.path.join(CURSOR_PROJECTS, proj, "agent-transcripts")
                if not os.path.isdir(transcripts_dir):
                    continue
                project_path = decode_cursor_project_folder_key(proj) or ("/" + proj.replace("-", "/"))

                for sess_dir in os.listdir(transcripts_dir):
                    sess_file = os.path.join(transcripts_dir, sess_dir, sess_dir + ".jsonl")
                    if not os.path.exists(sess_file):
                        continue
                    stat = os.stat(sess_file)
                    first_msg = ""
                    msg_count = 0
                    try:
                        first_line = read_lines(sess_file)[0] if read_lines(sess_file) else ""
                        if first_line:
                            d = _parse_json_line(first_line)
                            if d:
                                content = (d.get("message", {}) or {}).get("content")
                                if isinstance(content, list):
                                    for part in content:
                                        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                                            first_msg = re.sub(r"</?user_query>", "", part["text"]).strip()[:200]
                                            break
                        msg_count = len(read_lines(sess_file))
                    except (OSError, IndexError):
                        pass

                    sessions.append({
                        "id": sess_dir,
                        "tool": "cursor",
                        "project": project_path,
                        "project_short": project_path.replace(HOME, "~"),
                        "first_ts": stat.st_mtime * 1000 - (msg_count * 60000),
                        "last_ts": stat.st_mtime * 1000,
                        "messages": msg_count,
                        "first_message": first_msg,
                        "has_detail": True,
                        "file_size": stat.st_size,
                        "detail_messages": msg_count,
                        "_file": sess_file,
                    })
        except OSError:
            pass

    # Scan ~/.cursor/chats/*/
    if os.path.isdir(CURSOR_CHATS):
        try:
            for chat_dir_name in os.listdir(CURSOR_CHATS):
                full_dir = os.path.join(CURSOR_CHATS, chat_dir_name)
                if not os.path.isdir(full_dir):
                    continue
                for f in os.listdir(full_dir):
                    if not (f.endswith(".jsonl") or f.endswith(".json")):
                        continue
                    file_path = os.path.join(full_dir, f)
                    stat = os.stat(file_path)
                    first_msg = ""
                    msg_count = 0
                    try:
                        lines = read_lines(file_path)
                        if lines:
                            d = _parse_json_line(lines[0])
                            if d and d.get("role") == "user":
                                content = (d.get("message", {}) or {}).get("content") or d.get("content")
                                if isinstance(content, str):
                                    first_msg = content[:200]
                                elif isinstance(content, list):
                                    for p in content:
                                        if isinstance(p, dict) and p.get("text"):
                                            first_msg = re.sub(r"</?user_query>", "", p["text"]).strip()[:200]
                                            break
                        msg_count = len(lines)
                    except (OSError, IndexError):
                        pass

                    sessions.append({
                        "id": chat_dir_name,
                        "tool": "cursor",
                        "project": "",
                        "project_short": "",
                        "first_ts": stat.st_mtime * 1000 - (msg_count * 60000),
                        "last_ts": stat.st_mtime * 1000,
                        "messages": msg_count,
                        "first_message": first_msg,
                        "has_detail": True,
                        "file_size": stat.st_size,
                        "detail_messages": msg_count,
                        "_file": file_path,
                    })
                    break  # one file per chat dir
        except OSError:
            pass

    return sessions


def load_cursor_detail(session_id: str) -> dict:
    """Load Cursor session detail messages."""
    file_path = None

    # Search in projects
    if os.path.isdir(CURSOR_PROJECTS):
        for proj in os.listdir(CURSOR_PROJECTS):
            f = os.path.join(CURSOR_PROJECTS, proj, "agent-transcripts", session_id, session_id + ".jsonl")
            if os.path.exists(f):
                file_path = f
                break

    # Search in chats
    if not file_path and os.path.isdir(CURSOR_CHATS):
        chat_dir = os.path.join(CURSOR_CHATS, session_id)
        if os.path.isdir(chat_dir):
            for f in os.listdir(chat_dir):
                if f.endswith(".jsonl") or f.endswith(".json"):
                    file_path = os.path.join(chat_dir, f)
                    break

    if not file_path:
        return {"messages": []}

    messages = []
    lines = read_lines(file_path)
    for line in lines:
        d = _parse_json_line(line)
        if d is None:
            continue
        role = d.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = (d.get("message", {}) or {}).get("content") or d.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
            )
        # Strip Cursor wrappers
        text = re.sub(r"</?user_query>", "", text)
        text = re.sub(r"</?tool_call>", "", text)
        text = text.strip()
        if not text:
            continue
        messages.append({"role": role, "content": text[:2000], "uuid": ""})

    return {"messages": messages[:200]}


# ── Find Session File ──────────────────────────────────────

def find_session_file(session_id: str, project: str = "") -> dict | None:
    """Find session file across all agents. Returns {file, format} or None."""
    # Try Claude projects dir
    if project:
        project_key = re.sub(r"[^a-zA-Z0-9-]", "-", project)
        claude_file = os.path.join(PROJECTS_DIR, project_key, f"{session_id}.jsonl")
        if os.path.exists(claude_file):
            return {"file": claude_file, "format": "claude"}

    # Try all Claude project dirs
    if os.path.isdir(PROJECTS_DIR):
        for proj in os.listdir(PROJECTS_DIR):
            f = os.path.join(PROJECTS_DIR, proj, f"{session_id}.jsonl")
            if os.path.exists(f):
                return {"file": f, "format": "claude"}

    # Try Codex sessions dir
    codex_sessions_dir = os.path.join(CODEX_DIR, "sessions")
    if os.path.isdir(codex_sessions_dir):
        for root, _, files in os.walk(codex_sessions_dir):
            for fn in files:
                if session_id in fn and fn.endswith(".jsonl"):
                    return {"file": os.path.join(root, fn), "format": "codex"}

    # Try OpenCode (SQLite)
    if os.path.exists(OPENCODE_DB):
        return {"file": OPENCODE_DB, "format": "opencode", "sessionId": session_id}

    # Try Cursor
    if os.path.isdir(CURSOR_PROJECTS):
        for proj in os.listdir(CURSOR_PROJECTS):
            f = os.path.join(CURSOR_PROJECTS, proj, "agent-transcripts", session_id, session_id + ".jsonl")
            if os.path.exists(f):
                return {"file": f, "format": "cursor"}
    if os.path.isdir(CURSOR_CHATS):
        chat_dir = os.path.join(CURSOR_CHATS, session_id)
        if os.path.isdir(chat_dir):
            for f in os.listdir(chat_dir):
                if f.endswith(".jsonl") or f.endswith(".json"):
                    return {"file": os.path.join(chat_dir, f), "format": "cursor"}

    # Try Kiro (SQLite)
    if os.path.exists(KIRO_DB):
        try:
            conn = sqlite3.connect(KIRO_DB)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM conversations_v2 WHERE conversation_id = ?",
                (session_id,)
            )
            count = cursor.fetchone()[0]
            conn.close()
            if count > 0:
                return {"file": KIRO_DB, "format": "kiro", "sessionId": session_id}
        except (sqlite3.Error, OSError):
            pass

    return None


# ── Git Helpers ────────────────────────────────────────────

_git_root_cache: dict[str, str] = {}


def resolve_git_root(project_path: str) -> str:
    """Resolve git root for a project path, with caching."""
    if not project_path:
        return ""
    if project_path in _git_root_cache:
        return _git_root_cache[project_path]
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2
        )
        root = result.stdout.strip() if result.returncode == 0 else ""
        _git_root_cache[project_path] = root
        return root
    except (subprocess.TimeoutExpired, OSError):
        _git_root_cache[project_path] = ""
        return ""


_git_info_cache: dict[str, dict] = {}
GIT_INFO_CACHE_TTL = 30.0  # 30 seconds


def get_project_git_info(project_path: str) -> dict | None:
    """Get git info for a project path."""
    if not project_path or not os.path.exists(project_path):
        return None
    now = time.time()
    cached = _git_info_cache.get(project_path)
    if cached and (now - cached.get("_ts", 0)) < GIT_INFO_CACHE_TTL:
        return cached

    git_root = resolve_git_root(project_path)
    if not git_root:
        return None

    info = {"gitRoot": git_root, "branch": "", "remoteUrl": "", "lastCommit": "",
            "lastCommitDate": "", "isDirty": False, "_ts": now}

    def _git_cmd(args: list[str]) -> str:
        try:
            r = subprocess.run(
                ["git", "-C", git_root] + args,
                capture_output=True, text=True, timeout=3
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except (subprocess.TimeoutExpired, OSError):
            return ""

    info["branch"] = _git_cmd(["rev-parse", "--abbrev-ref", "HEAD"])
    info["remoteUrl"] = _git_cmd(["config", "--get", "remote.origin.url"])
    log_line = _git_cmd(["log", "-1", "--format=%h %s"])
    if log_line:
        sp = log_line.find(" ")
        if sp > 0:
            info["lastCommitHash"] = log_line[:sp]
            info["lastCommit"] = log_line[sp + 1:][:80]
        else:
            info["lastCommit"] = log_line
    info["lastCommitDate"] = _git_cmd(["log", "-1", "--format=%ci"])
    status = _git_cmd(["status", "--porcelain"])
    info["isDirty"] = len(status) > 0

    _git_info_cache[project_path] = info
    return info


def get_git_commits(project_dir: str, from_ts: float, to_ts: float) -> list[dict]:
    """Get git commits in a time range."""
    if not project_dir or not os.path.exists(project_dir):
        return []
    try:
        after_date = datetime.fromtimestamp(from_ts / 1000).isoformat()
        before_date = datetime.fromtimestamp(to_ts / 1000).isoformat()
        result = subprocess.run(
            ["git", "log", "--oneline", f"--after={after_date}", f"--before={before_date}"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        commits = []
        for line in result.stdout.strip().split("\n"):
            sp = line.find(" ")
            if sp == -1:
                commits.append({"hash": line, "message": ""})
            else:
                commits.append({"hash": line[:sp], "message": line[sp + 1:]})
        return commits
    except (subprocess.TimeoutExpired, OSError):
        return []


# ── Main Session Loading ───────────────────────────────────

_sessions_cache: list[dict] | None = None
_sessions_cache_ts: float = 0
SESSIONS_CACHE_TTL = 10.0  # 10 seconds


def load_sessions() -> list[dict]:
    """Load all sessions from all 6 agents."""
    global _sessions_cache, _sessions_cache_ts
    now = time.time()
    if _sessions_cache is not None and (now - _sessions_cache_ts) < SESSIONS_CACHE_TTL:
        return _sessions_cache

    sessions: dict[str, dict] = {}

    # 1. Claude Code sessions from history.jsonl
    if os.path.exists(HISTORY_FILE):
        lines = read_lines(HISTORY_FILE)
        for line in lines:
            d = _parse_json_line(line)
            if d is None:
                continue
            sid = d.get("sessionId")
            if not sid:
                continue
            if sid not in sessions:
                sessions[sid] = {
                    "id": sid,
                    "tool": "claude",
                    "project": d.get("project", ""),
                    "project_short": (d.get("project", "")).replace(HOME, "~"),
                    "first_ts": d.get("timestamp", 0),
                    "last_ts": d.get("timestamp", 0),
                    "messages": 0,
                    "first_message": "",
                    "_claude_dir": CLAUDE_DIR,
                }
            s = sessions[sid]
            s["last_ts"] = max(s["last_ts"], d.get("timestamp", 0))
            s["first_ts"] = min(s["first_ts"], d.get("timestamp", 0))
            s["messages"] += 1
            display = d.get("display", "")
            if display and display != "exit" and not s["first_message"]:
                s["first_message"] = display[:200]

    # 2. Codex sessions
    if os.path.isdir(CODEX_DIR):
        try:
            for cs in scan_codex_sessions():
                sessions[cs["id"]] = cs
        except Exception:
            pass

    # 3. OpenCode sessions
    try:
        for ocs in scan_opencode_sessions():
            sessions[ocs["id"]] = ocs
    except Exception:
        pass

    # 4. Cursor sessions
    try:
        for cs in scan_cursor_sessions():
            sessions[cs["id"]] = cs
    except Exception:
        pass

    # 5. Kiro sessions
    try:
        for ks in scan_kiro_sessions():
            sessions[ks["id"]] = ks
    except Exception:
        pass

    # 6. Enrich Claude sessions with detail files
    for sid, s in list(sessions.items()):
        if s.get("tool") not in ("claude", "claude-ext"):
            continue
        session_file = ""
        if s.get("_session_file") and os.path.exists(s["_session_file"]):
            session_file = s["_session_file"]
        elif s.get("project"):
            claude_dir = s.get("_claude_dir", CLAUDE_DIR)
            projects_dir = os.path.join(claude_dir, "projects")
            project_key = re.sub(r"[^a-zA-Z0-9-]", "-", s["project"])
            candidate = os.path.join(projects_dir, project_key, f"{sid}.jsonl")
            if os.path.exists(candidate):
                session_file = candidate
        if not session_file:
            found = find_session_file(sid, s.get("project", ""))
            if found and found["format"] == "claude":
                session_file = found["file"]

        if session_file and os.path.exists(session_file):
            summary = parse_claude_session_file(session_file)
            if summary:
                merge_claude_session_detail(s, summary, session_file)
            else:
                s["has_detail"] = True
                s["file_size"] = os.stat(session_file).st_size
                s["_session_file"] = session_file
        elif not s.get("has_detail"):
            s["has_detail"] = False
            s["file_size"] = 0
            s["detail_messages"] = 0

    # 7. Scan orphan sessions from projects dir
    if os.path.isdir(PROJECTS_DIR):
        try:
            for proj in os.listdir(PROJECTS_DIR):
                proj_dir = os.path.join(PROJECTS_DIR, proj)
                if not os.path.isdir(proj_dir):
                    continue
                for fn in os.listdir(proj_dir):
                    if not fn.endswith(".jsonl"):
                        continue
                    sid = fn[:-6]  # strip .jsonl
                    file_path = os.path.join(proj_dir, fn)
                    if sid in sessions:
                        summary = parse_claude_session_file(file_path)
                        if summary:
                            merge_claude_session_detail(sessions[sid], summary, file_path)
                        continue
                    summary = parse_claude_session_file(file_path)
                    if not summary:
                        continue
                    sessions[sid] = {
                        "id": sid,
                        "tool": summary["tool"],
                        "project": summary["projectPath"],
                        "project_short": summary["projectPath"].replace(HOME, "~") if summary["projectPath"] else "",
                        "first_ts": summary["firstTs"],
                        "last_ts": summary["lastTs"],
                        "messages": summary["msgCount"],
                        "first_message": summary["customTitle"] or summary["firstMsg"],
                        "has_detail": True,
                        "file_size": summary["fileSize"],
                        "detail_messages": summary["msgCount"],
                        "_claude_dir": CLAUDE_DIR,
                        "_session_file": file_path,
                        "worktree_original_cwd": summary.get("worktreeOriginalCwd", ""),
                    }
        except OSError:
            pass

    # Sort by last_ts descending
    result = sorted(sessions.values(), key=lambda s: s.get("last_ts", 0), reverse=True)

    # Resolve git roots
    unique_paths = {s.get("project", "") for s in result if s.get("project")}
    for p in unique_paths:
        resolve_git_root(p)

    # Format dates
    for s in result:
        last_ts = s.get("last_ts", 0)
        first_ts = s.get("first_ts", 0)
        try:
            if last_ts > 0:
                dt = datetime.fromtimestamp(last_ts / 1000 if last_ts > 1e12 else last_ts)
                s["last_time"] = dt.strftime("%Y-%m-%d %H:%M")
                s["date"] = dt.strftime("%Y-%m-%d")
            if first_ts > 0:
                ft = datetime.fromtimestamp(first_ts / 1000 if first_ts > 1e12 else first_ts)
                s["first_time"] = ft.strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            s["last_time"] = ""
            s["first_time"] = ""
            s["date"] = ""

        s["git_root"] = s.get("worktree_original_cwd", "") or (
            _git_root_cache.get(s.get("project", ""), "") if s.get("project") else ""
        )

    _sessions_cache = result
    _sessions_cache_ts = time.time()
    return result


def load_session_detail(session_id: str, project: str = "") -> dict:
    """Load full session messages."""
    found = find_session_file(session_id, project)
    if not found:
        return {"error": "Session file not found", "messages": []}

    if found["format"] == "opencode":
        return load_opencode_detail(session_id)
    if found["format"] == "cursor":
        return load_cursor_detail(session_id)
    if found["format"] == "kiro":
        return load_kiro_detail(session_id)

    messages = []
    lines = read_lines(found["file"])

    for line in lines:
        entry = _parse_json_line(line)
        if entry is None:
            continue

        if found["format"] == "claude":
            if entry.get("type") in ("user", "assistant"):
                content = extract_content((entry.get("message", {}) or {}).get("content"))
                if content:
                    messages.append({
                        "role": entry["type"],
                        "content": content[:2000],
                        "uuid": entry.get("uuid", ""),
                    })
        else:  # codex
            if entry.get("type") == "response_item" and entry.get("payload"):
                role = entry["payload"].get("role", "")
                if role in ("user", "assistant"):
                    content = extract_content(entry["payload"].get("content"))
                    if content and not is_system_message(content):
                        messages.append({"role": role, "content": content[:2000], "uuid": ""})

    return {"messages": messages[:200]}


def delete_session(session_id: str, project: str = "") -> list[str]:
    """Delete a session and return list of deleted items."""
    deleted = []
    project_key = re.sub(r"[^a-zA-Z0-9-]", "-", project)
    session_file = os.path.join(PROJECTS_DIR, project_key, f"{session_id}.jsonl")
    if os.path.exists(session_file):
        os.unlink(session_file)
        deleted.append("session file")

    session_dir = os.path.join(PROJECTS_DIR, project_key, session_id)
    if os.path.isdir(session_dir):
        import shutil
        shutil.rmtree(session_dir)
        deleted.append("session dir")

    if os.path.exists(HISTORY_FILE):
        lines = read_lines(HISTORY_FILE)
        filtered = []
        removed = 0
        for line in lines:
            d = _parse_json_line(line)
            if d and d.get("sessionId") == session_id:
                removed += 1
            else:
                filtered.append(line)
        if removed > 0:
            with open(HISTORY_FILE, "w") as f:
                f.write("\n".join(filtered) + "\n")
            deleted.append(f"{removed} history entries")

    env_file = os.path.join(CLAUDE_DIR, "session-env", f"{session_id}.json")
    if os.path.exists(env_file):
        os.unlink(env_file)
        deleted.append("env file")

    # Clear cache
    global _sessions_cache
    _sessions_cache = None

    return deleted


def get_session_preview(session_id: str, project: str = "", limit: int = 10) -> list[dict]:
    """Get first N messages as preview."""
    found = find_session_file(session_id, project)
    if not found:
        return []

    if found["format"] == "cursor":
        detail = load_cursor_detail(session_id)
        return [{"role": m["role"], "content": m["content"][:300]} for m in detail["messages"][:limit]]
    if found["format"] == "kiro":
        detail = load_kiro_detail(session_id)
        return [{"role": m["role"], "content": m["content"][:300]} for m in detail["messages"][:limit]]
    if found["format"] == "opencode":
        detail = load_opencode_detail(session_id)
        return [{"role": m["role"], "content": m["content"][:300]} for m in detail["messages"][:limit]]

    messages = []
    lines = read_lines(found["file"])
    for line in lines:
        if len(messages) >= limit:
            break
        entry = _parse_json_line(line)
        if entry is None:
            continue
        if found["format"] == "claude":
            if entry.get("type") in ("user", "assistant"):
                content = extract_content((entry.get("message", {}) or {}).get("content"))
                if content:
                    messages.append({"role": entry["type"], "content": content[:300]})
        else:
            if entry.get("type") == "response_item" and entry.get("payload"):
                role = entry["payload"].get("role", "")
                if role in ("user", "assistant"):
                    content = extract_content(entry["payload"].get("content"))
                    if content and not is_system_message(content):
                        messages.append({"role": role, "content": content[:300]})
    return messages


def get_session_replay(session_id: str, project: str = "") -> dict:
    """Get session messages with timestamps for replay."""
    found = find_session_file(session_id, project)
    if not found:
        return {"messages": [], "duration": 0}

    messages = []
    lines = read_lines(found["file"])
    for line in lines:
        entry = _parse_json_line(line)
        if entry is None:
            continue
        role = ""
        content = ""
        ts = ""
        if found["format"] == "claude":
            if entry.get("type") not in ("user", "assistant"):
                continue
            role = entry["type"]
            content = extract_content((entry.get("message", {}) or {}).get("content"))
            ts = entry.get("timestamp", "")
        else:
            if entry.get("type") != "response_item" or not entry.get("payload"):
                continue
            role = entry["payload"].get("role", "")
            if role not in ("user", "assistant"):
                continue
            content = extract_content(entry["payload"].get("content"))
            ts = entry.get("timestamp", "")

        if not content or is_system_message(content):
            continue

        ms = 0
        if ts:
            try:
                if isinstance(ts, (int, float)):
                    ms = ts if ts > 1e12 else ts * 1000
                else:
                    ms = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp() * 1000
            except (ValueError, TypeError):
                pass

        messages.append({
            "role": role,
            "content": content[:3000],
            "timestamp": ts,
            "ms": ms,
        })

    start_ms = messages[0]["ms"] if messages else 0
    end_ms = messages[-1]["ms"] if messages else 0

    return {
        "messages": messages,
        "startMs": start_ms,
        "endMs": end_ms,
        "duration": end_ms - start_ms,
    }


def export_session_markdown(session_id: str, project: str = "") -> str:
    """Export session as Markdown."""
    found = find_session_file(session_id, project)
    if not found or found["format"] != "claude" or not os.path.exists(found["file"]):
        return f"# Session {session_id}\n\nSession file not found.\n"

    summary = parse_claude_session_file(found["file"])
    lines_data = read_lines(found["file"])
    project_label = project or (summary["projectPath"] if summary else "") or "(none)"
    parts = [f"# Session {session_id}\n\n**Project:** {project_label}\n"]

    for line in lines_data:
        entry = _parse_json_line(line)
        if entry is None:
            continue
        if entry.get("type") in ("user", "assistant"):
            msg = entry.get("message", {}) or {}
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    (b if isinstance(b, str) else (b.get("text", "") if b.get("type") == "text" else ""))
                    for b in content
                    if isinstance(b, str) or (isinstance(b, dict) and b.get("type") == "text")
                )
            header = "## User" if entry["type"] == "user" else "## Assistant"
            parts.append(f"\n{header}\n\n{content}\n")

    return "".join(parts)
