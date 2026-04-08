"""Full-text search index with rapidfuzz fuzzy matching."""

import time

from rapidfuzz import fuzz

from .data import find_session_file, read_lines, extract_content, is_system_message, _parse_json_line

# ── Search Index ───────────────────────────────────────────

_search_index: list[dict] | None = None
_search_index_built_at: float = 0
INDEX_TTL = 60.0  # rebuild every 60s


def build_search_index(sessions: list[dict]) -> list[dict]:
    """Build in-memory search index from all sessions."""
    start_ms = time.time()
    index = []

    for s in sessions:
        if not s.get("has_detail"):
            continue
        found = find_session_file(s["id"], s.get("project", ""))
        if not found:
            continue

        try:
            lines = read_lines(found["file"])
            texts = []
            for line in lines:
                entry = _parse_json_line(line)
                if entry is None:
                    continue
                role = ""
                content = ""
                if found["format"] == "claude":
                    if entry.get("type") not in ("user", "assistant"):
                        continue
                    role = entry["type"]
                    content = extract_content((entry.get("message", {}) or {}).get("content"))
                else:
                    if entry.get("type") != "response_item" or not entry.get("payload"):
                        continue
                    role = entry["payload"].get("role", "")
                    if role not in ("user", "assistant"):
                        continue
                    content = extract_content(entry["payload"].get("content"))

                if content and not is_system_message(content):
                    texts.append({"role": role, "content": content[:500]})

            if texts:
                full_text = " ".join(t["content"] for t in texts).lower()
                index.append({"sessionId": s["id"], "texts": texts, "fullText": full_text})
        except (OSError, Exception):
            pass

    elapsed = time.time() - start_ms
    return index


def get_search_index(sessions: list[dict]) -> list[dict]:
    """Get cached search index, rebuilding if expired."""
    global _search_index, _search_index_built_at
    now = time.time()
    if _search_index is None or (now - _search_index_built_at) > INDEX_TTL:
        _search_index = build_search_index(sessions)
        _search_index_built_at = now
    return _search_index


def search_full_text(query: str, sessions: list[dict]) -> list[dict]:
    """Search across all sessions with substring matching and snippets."""
    if not query or len(query) < 2:
        return []

    q = query.lower()
    index = get_search_index(sessions)
    results = []

    for entry in index:
        if q not in entry["fullText"]:
            continue

        matches = []
        for t in entry["texts"]:
            if len(matches) >= 3:
                break
            idx = t["content"].lower().find(q)
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(t["content"]), idx + len(q) + 50)
                snippet = ("..." if start > 0 else "") + t["content"][start:end] + ("..." if end < len(t["content"]) else "")
                matches.append({"role": t["role"], "snippet": snippet})

        if matches:
            results.append({"sessionId": entry["sessionId"], "matches": matches})

    return results


def fuzzy_search(query: str, sessions: list[dict], threshold: int = 60) -> list[dict]:
    """Fuzzy search using rapidfuzz."""
    if not query or len(query) < 2:
        return []

    results = []
    for s in sessions:
        title = s.get("first_message", "")
        project = s.get("project_short", "") or s.get("project", "")
        text = f"{title} {project}".strip()
        if not text:
            continue

        score = fuzz.partial_ratio(query.lower(), text.lower())
        if score >= threshold:
            results.append({"sessionId": s["id"], "score": score, "text": text})

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:50]
