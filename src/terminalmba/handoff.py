"""Handoff document generation."""

from .data import load_sessions, load_session_detail
from .cost import compute_session_cost

VERBOSITY = {
    "minimal": 3,
    "standard": 10,
    "verbose": 20,
    "full": 50,
}


def generate_handoff(session_id: str, project: str = "", options: dict | None = None) -> dict:
    """Generate a handoff markdown document for a session."""
    options = options or {}
    verbosity = options.get("verbosity", "standard")
    target = options.get("target", "any")
    msg_limit = VERBOSITY.get(verbosity, 10)

    sessions = load_sessions()
    session = next(
        (s for s in sessions if s["id"] == session_id or s["id"].startswith(session_id)),
        None
    )
    if not session:
        return {"ok": False, "error": "Session not found"}

    detail = load_session_detail(session["id"], session.get("project", "") or project)
    messages = (detail.get("messages") or [])[-msg_limit:]
    cost = compute_session_cost(session["id"], session.get("project", "") or project)

    lines = []
    lines.append("# Session Handoff")
    lines.append("")
    lines.append(f"> Transferred from **{session.get('tool', '')}** session `{session['id']}`")
    lines.append(f"> Project: `{session.get('project_short', '') or session.get('project', '') or 'unknown'}`")
    lines.append(f"> Started: {session.get('first_time', '')} | Last active: {session.get('last_time', '')}")
    lines.append(f"> Messages: {session.get('detail_messages', 0) or session.get('messages', 0)} | Cost: ${cost['cost']:.2f} ({cost.get('model', '') or 'unknown'})")
    lines.append("")

    if messages:
        first_user = next((m for m in messages if m.get("role") == "user"), None)
        if first_user:
            lines.append("## Original Task")
            lines.append("")
            lines.append(first_user.get("content", "")[:500])
            lines.append("")

        last_assistant = next(
            (m for m in reversed(messages) if m.get("role") == "assistant"), None
        )
        if last_assistant:
            lines.append("## Current State (last assistant response)")
            lines.append("")
            lines.append(last_assistant.get("content", "")[:1000])
            lines.append("")

        last_user = next(
            (m for m in reversed(messages) if m.get("role") == "user"), None
        )
        if last_user and last_user != first_user:
            lines.append("## Latest Request")
            lines.append("")
            lines.append(last_user.get("content", "")[:500])
            lines.append("")

    lines.append("## Recent Conversation")
    lines.append("")
    for m in messages:
        role_label = "User" if m.get("role") == "user" else "Assistant"
        lines.append(f"### {role_label}")
        lines.append("")
        max_len = 3000 if verbosity == "full" else 1000
        lines.append(m.get("content", "")[:max_len])
        lines.append("")

    lines.append("## Instructions for New Agent")
    lines.append("")
    lines.append("This is a handoff from a previous coding session. Please:")
    lines.append("1. Read the context above to understand what was being worked on")
    lines.append("2. Continue from where the previous agent left off")
    lines.append("3. Do not repeat work that was already completed")
    if session.get("project"):
        lines.append(f"4. The project directory is: `{session['project']}`")
    lines.append("")

    markdown = "\n".join(lines)

    return {
        "ok": True,
        "markdown": markdown,
        "session": {
            "id": session["id"],
            "tool": session.get("tool", ""),
            "project": session.get("project_short", "") or session.get("project", ""),
            "messages": len(messages),
        },
        "target": target,
    }


def quick_handoff(source_tool: str, target: str = "any", options: dict | None = None) -> dict:
    """Find latest session of a tool and generate handoff."""
    sessions = load_sessions()
    source = next((s for s in sessions if s.get("tool") == source_tool), None)
    if not source:
        return {"ok": False, "error": f"No {source_tool} sessions found"}
    return generate_handoff(source["id"], source.get("project", ""), {**(options or {}), "target": target})
