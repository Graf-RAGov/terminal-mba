"""Cross-agent session conversion (Claude <-> Codex)."""

import os
import uuid
from datetime import datetime
from pathlib import Path

import orjson

from .data import (
    find_session_file, extract_content, is_system_message, read_lines, _parse_json_line,
    CLAUDE_DIR, CODEX_DIR, HOME,
)


def read_session(session_id: str, project: str = "") -> dict | None:
    """Read session into canonical format."""
    found = find_session_file(session_id, project)
    if not found:
        return None

    messages = []
    lines = read_lines(found["file"])
    session_meta: dict = {}

    for line in lines:
        entry = _parse_json_line(line)
        if entry is None:
            continue

        if found["format"] == "claude":
            if entry.get("type") == "permission-mode":
                session_meta["permissionMode"] = entry.get("permissionMode")
                session_meta["originalSessionId"] = entry.get("sessionId")
            if entry.get("type") in ("user", "assistant"):
                msg = entry.get("message", {}) or {}
                content = ""
                raw = msg.get("content", "")
                if isinstance(raw, str):
                    content = raw
                elif isinstance(raw, list):
                    content = "\n".join(
                        b.get("text", "") for b in raw
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                if not content or is_system_message(content):
                    continue
                messages.append({
                    "role": "user" if entry["type"] == "user" else "assistant",
                    "content": content,
                    "timestamp": entry.get("timestamp", ""),
                    "model": msg.get("model", ""),
                })
        else:
            # Codex
            if entry.get("type") == "session_meta" and entry.get("payload"):
                session_meta["cwd"] = entry["payload"].get("cwd", "")
                session_meta["originalSessionId"] = entry["payload"].get("id", "")
            if entry.get("type") == "response_item" and entry.get("payload"):
                role = entry["payload"].get("role", "")
                if role not in ("user", "assistant"):
                    continue
                content = extract_content(entry["payload"].get("content"))
                if not content or is_system_message(content):
                    continue
                messages.append({
                    "role": role,
                    "content": content,
                    "timestamp": entry.get("timestamp", ""),
                    "model": "",
                })

    return {
        "sourceFormat": found["format"],
        "sourceFile": found["file"],
        "sessionId": session_id,
        "meta": session_meta,
        "messages": messages,
    }


def write_claude(canonical: dict, target_project: str = "") -> dict:
    """Write as Claude Code session."""
    new_session_id = str(uuid.uuid4())
    project_key_path = target_project or HOME
    project_key = project_key_path.replace("/", "-").replace(".", "-")
    project_dir = os.path.join(CLAUDE_DIR, "projects", project_key)
    os.makedirs(project_dir, exist_ok=True)

    out_file = os.path.join(project_dir, f"{new_session_id}.jsonl")
    cwd = target_project or canonical["meta"].get("cwd", "") or HOME
    lines = []

    # Permission mode entry
    lines.append(orjson.dumps({
        "type": "permission-mode",
        "permissionMode": "default",
        "sessionId": new_session_id,
    }).decode())

    prev_uuid = None
    for msg in canonical["messages"]:
        msg_uuid = str(uuid.uuid4())
        entry = {
            "parentUuid": prev_uuid,
            "isSidechain": False,
            "type": "user" if msg["role"] == "user" else "assistant",
            "uuid": msg_uuid,
            "timestamp": msg.get("timestamp") or datetime.now().isoformat(),
            "userType": "external",
            "entrypoint": "cli",
            "cwd": cwd,
            "sessionId": new_session_id,
            "version": "2.1.91",
            "gitBranch": "main",
        }
        if msg["role"] == "user":
            entry["message"] = {"role": "user", "content": msg["content"]}
            entry["promptId"] = str(uuid.uuid4())
        else:
            entry["message"] = {
                "model": msg.get("model") or "claude-sonnet-4-6",
                "id": f"msg_converted_{msg_uuid[:8]}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": msg["content"]}],
                "stop_reason": "end_turn",
            }
        lines.append(orjson.dumps(entry).decode())
        prev_uuid = msg_uuid

    # Write atomically
    tmp_file = out_file + ".tmp"
    with open(tmp_file, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.rename(tmp_file, out_file)

    # Add to history.jsonl
    history_file = os.path.join(CLAUDE_DIR, "history.jsonl")
    first_content = canonical["messages"][0]["content"][:100] if canonical["messages"] else ""
    history_entry = orjson.dumps({
        "sessionId": new_session_id,
        "project": cwd,
        "timestamp": int(datetime.now().timestamp() * 1000),
        "display": f"[Converted from {canonical['sourceFormat']}] {first_content}",
        "pastedContents": {},
    }).decode()
    with open(history_file, "a") as f:
        f.write(history_entry + "\n")

    return {
        "sessionId": new_session_id,
        "file": out_file,
        "format": "claude",
        "messages": len(canonical["messages"]),
        "resumeCmd": f"claude --resume {new_session_id}",
    }


def write_codex(canonical: dict, target_project: str = "") -> dict:
    """Write as Codex session."""
    new_session_id = str(uuid.uuid4())
    now = datetime.now()
    date_dir = os.path.join(
        CODEX_DIR, "sessions",
        str(now.year),
        str(now.month).zfill(2),
        str(now.day).zfill(2),
    )
    os.makedirs(date_dir, exist_ok=True)

    file_name = f"rollout-{now.strftime('%Y-%m-%dT%H-%M-%S')}-{new_session_id}.jsonl"
    out_file = os.path.join(date_dir, file_name)
    cwd = target_project or canonical["meta"].get("cwd", "") or HOME
    lines = []

    # Session meta
    lines.append(orjson.dumps({
        "timestamp": now.isoformat(),
        "type": "session_meta",
        "payload": {
            "id": new_session_id,
            "timestamp": now.isoformat(),
            "cwd": cwd,
            "originator": "codex_cli_rs",
            "cli_version": "0.101.0",
            "source": "cli",
            "model_provider": "openai",
        },
    }).decode())

    # Messages
    for msg in canonical["messages"]:
        lines.append(orjson.dumps({
            "timestamp": msg.get("timestamp") or now.isoformat(),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": msg["role"],
                "content": [{"type": "input_text", "text": msg["content"]}],
            },
        }).decode())

    # Write atomically
    tmp_file = out_file + ".tmp"
    with open(tmp_file, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.rename(tmp_file, out_file)

    # Add to codex history
    history_file = os.path.join(CODEX_DIR, "history.jsonl")
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    first_content = canonical["messages"][0]["content"][:100] if canonical["messages"] else ""
    history_entry = orjson.dumps({
        "session_id": new_session_id,
        "ts": int(datetime.now().timestamp()),
        "text": f"[Converted from {canonical['sourceFormat']}] {first_content}",
    }).decode()
    with open(history_file, "a") as f:
        f.write(history_entry + "\n")

    return {
        "sessionId": new_session_id,
        "file": out_file,
        "format": "codex",
        "messages": len(canonical["messages"]),
        "resumeCmd": f"codex resume {new_session_id}",
    }


def convert_session(session_id: str, project: str = "", target_format: str = "") -> dict:
    """Convert session between agent formats."""
    canonical = read_session(session_id, project)
    if not canonical:
        return {"ok": False, "error": "Session not found"}

    if canonical["sourceFormat"] == target_format:
        return {"ok": False, "error": f"Session is already in {target_format} format"}

    if not canonical["messages"]:
        return {"ok": False, "error": "Session has no messages to convert"}

    if target_format == "claude":
        result = write_claude(canonical, project)
    elif target_format == "codex":
        result = write_codex(canonical, project)
    else:
        return {"ok": False, "error": f"Unknown target format: {target_format}"}

    return {
        "ok": True,
        "source": {
            "format": canonical["sourceFormat"],
            "sessionId": session_id,
            "messages": len(canonical["messages"]),
        },
        "target": result,
    }
