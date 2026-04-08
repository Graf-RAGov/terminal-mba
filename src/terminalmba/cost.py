"""Cost calculation with per-model pricing."""

import os
import sqlite3
import time

import orjson

from .data import (
    find_session_file, read_lines, _parse_json_line,
    OPENCODE_DB, HOME,
)

CONTEXT_WINDOW = 200_000  # Claude's max context window (tokens)

# ── Pricing per model (per token, April 2026) ─────────────

MODEL_PRICING = {
    "claude-opus-4-6": {"input": 5.00 / 1e6, "output": 25.00 / 1e6, "cache_read": 0.50 / 1e6, "cache_create": 6.25 / 1e6},
    "claude-opus-4-5": {"input": 5.00 / 1e6, "output": 25.00 / 1e6, "cache_read": 0.50 / 1e6, "cache_create": 6.25 / 1e6},
    "claude-sonnet-4-6": {"input": 3.00 / 1e6, "output": 15.00 / 1e6, "cache_read": 0.30 / 1e6, "cache_create": 3.75 / 1e6},
    "claude-sonnet-4-5": {"input": 3.00 / 1e6, "output": 15.00 / 1e6, "cache_read": 0.30 / 1e6, "cache_create": 3.75 / 1e6},
    "claude-haiku-4-5": {"input": 1.00 / 1e6, "output": 5.00 / 1e6, "cache_read": 0.10 / 1e6, "cache_create": 1.25 / 1e6},
    "codex-mini-latest": {"input": 1.50 / 1e6, "output": 6.00 / 1e6, "cache_read": 0.375 / 1e6, "cache_create": 1.875 / 1e6},
    "gpt-5": {"input": 1.25 / 1e6, "output": 10.00 / 1e6, "cache_read": 0.625 / 1e6, "cache_create": 1.25 / 1e6},
}


def get_model_pricing(model: str) -> dict:
    """Get pricing for a model with fallback matching."""
    if not model:
        return MODEL_PRICING["claude-sonnet-4-6"]
    for key, pricing in MODEL_PRICING.items():
        if key in model or model.startswith(key):
            return pricing
    if "opus" in model:
        return MODEL_PRICING["claude-opus-4-6"]
    if "haiku" in model:
        return MODEL_PRICING["claude-haiku-4-5"]
    if "sonnet" in model:
        return MODEL_PRICING["claude-sonnet-4-6"]
    if "codex" in model:
        return MODEL_PRICING["codex-mini-latest"]
    return MODEL_PRICING["claude-sonnet-4-6"]


def compute_session_cost(session_id: str, project: str = "") -> dict:
    """Compute real cost from session file token usage."""
    found = find_session_file(session_id, project)
    zero = {"cost": 0, "inputTokens": 0, "outputTokens": 0, "cacheReadTokens": 0,
            "cacheCreateTokens": 0, "contextPctSum": 0, "contextTurnCount": 0, "model": ""}
    if not found:
        return zero

    total_cost = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0
    context_pct_sum = 0
    context_turn_count = 0
    model = ""

    # OpenCode: query SQLite directly
    if found["format"] == "opencode":
        if not os.path.exists(OPENCODE_DB):
            return zero
        try:
            conn = sqlite3.connect(OPENCODE_DB)
            cursor = conn.execute(
                "SELECT data FROM message WHERE session_id = ? AND json_extract(data, '$.role') = 'assistant' ORDER BY time_created",
                (session_id,)
            )
            for (row_data,) in cursor:
                try:
                    msg_data = orjson.loads(row_data)
                    t = msg_data.get("tokens", {})
                    if not model and msg_data.get("modelID"):
                        model = msg_data["modelID"]
                    inp = t.get("input", 0)
                    out = (t.get("output", 0)) + (t.get("reasoning", 0))
                    cache_read = (t.get("cache", {}) or {}).get("read", 0)
                    cache_create = (t.get("cache", {}) or {}).get("write", 0)
                    if inp == 0 and out == 0:
                        continue
                    pricing = get_model_pricing(msg_data.get("modelID", "") or model)
                    total_input += inp
                    total_output += out
                    total_cache_read += cache_read
                    total_cache_create += cache_create
                    total_cost += (inp * pricing["input"]
                                   + cache_create * pricing["cache_create"]
                                   + cache_read * pricing["cache_read"]
                                   + out * pricing["output"])
                    ctx = inp + cache_create + cache_read
                    if ctx > 0:
                        context_pct_sum += (ctx / CONTEXT_WINDOW) * 100
                        context_turn_count += 1
                except (orjson.JSONDecodeError, ValueError):
                    pass
            conn.close()
        except (sqlite3.Error, OSError):
            pass
        return {"cost": total_cost, "inputTokens": total_input, "outputTokens": total_output,
                "cacheReadTokens": total_cache_read, "cacheCreateTokens": total_cache_create,
                "contextPctSum": context_pct_sum, "contextTurnCount": context_turn_count, "model": model}

    try:
        lines = read_lines(found["file"])
        for line in lines:
            entry = _parse_json_line(line)
            if entry is None:
                continue
            if found["format"] == "claude" and entry.get("type") == "assistant":
                msg = entry.get("message", {}) or {}
                if not model and msg.get("model"):
                    model = msg["model"]
                u = msg.get("usage")
                if not u:
                    continue
                pricing = get_model_pricing(msg.get("model", "") or model)
                inp = u.get("input_tokens", 0)
                cache_create = u.get("cache_creation_input_tokens", 0)
                cache_read = u.get("cache_read_input_tokens", 0)
                out = u.get("output_tokens", 0)

                total_input += inp
                total_output += out
                total_cache_read += cache_read
                total_cache_create += cache_create
                total_cost += (inp * pricing["input"]
                               + cache_create * pricing["cache_create"]
                               + cache_read * pricing["cache_read"]
                               + out * pricing["output"])
                ctx = inp + cache_create + cache_read
                if ctx > 0:
                    context_pct_sum += (ctx / CONTEXT_WINDOW) * 100
                    context_turn_count += 1
    except (OSError, Exception):
        pass

    # Fallback for Codex
    if total_cost == 0 and found["format"] == "codex":
        try:
            size = os.stat(found["file"]).st_size
            tokens = size / 4
            pricing = MODEL_PRICING["codex-mini-latest"]
            total_input = round(tokens * 0.3)
            total_output = round(tokens * 0.7)
            total_cost = total_input * pricing["input"] + total_output * pricing["output"]
        except OSError:
            pass

    return {"cost": total_cost, "inputTokens": total_input, "outputTokens": total_output,
            "cacheReadTokens": total_cache_read, "cacheCreateTokens": total_cache_create,
            "contextPctSum": context_pct_sum, "contextTurnCount": context_turn_count, "model": model}


def get_cost_analytics(sessions: list[dict]) -> dict:
    """Get aggregated cost analytics."""
    by_day: dict = {}
    by_project: dict = {}
    by_week: dict = {}
    by_agent: dict = {}
    total_cost = 0
    total_tokens = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read_tokens = 0
    total_cache_create_tokens = 0
    global_context_pct_sum = 0
    global_context_turn_count = 0
    first_date = None
    last_date = None
    sessions_with_data = 0
    agent_no_cost_data: dict = {}
    session_costs = []

    for s in sessions:
        if s.get("tool") and s["tool"] not in by_agent:
            by_agent[s["tool"]] = {"cost": 0, "sessions": 0, "tokens": 0, "estimated": False}

    for s in sessions:
        cost_data = compute_session_cost(s["id"], s.get("project", ""))
        cost = cost_data["cost"]
        tokens = (cost_data["inputTokens"] + cost_data["outputTokens"]
                  + cost_data["cacheReadTokens"] + cost_data["cacheCreateTokens"])
        if cost == 0 and tokens == 0:
            tool = s.get("tool", "")
            if tool not in agent_no_cost_data:
                agent_no_cost_data[tool] = 0
            agent_no_cost_data[tool] += 1
            continue

        sessions_with_data += 1
        total_cost += cost
        total_tokens += tokens
        total_input_tokens += cost_data["inputTokens"]
        total_output_tokens += cost_data["outputTokens"]
        total_cache_read_tokens += cost_data["cacheReadTokens"]
        total_cache_create_tokens += cost_data["cacheCreateTokens"]

        agent = s.get("tool", "unknown")
        if agent not in by_agent:
            by_agent[agent] = {"cost": 0, "sessions": 0, "tokens": 0, "estimated": False}
        by_agent[agent]["cost"] += cost
        by_agent[agent]["sessions"] += 1
        by_agent[agent]["tokens"] += tokens
        if agent == "codex":
            by_agent[agent]["estimated"] = True

        global_context_pct_sum += cost_data["contextPctSum"]
        global_context_turn_count += cost_data["contextTurnCount"]

        day = s.get("date", "unknown")
        if s.get("date"):
            if not first_date or s["date"] < first_date:
                first_date = s["date"]
            if not last_date or s["date"] > last_date:
                last_date = s["date"]

        if day not in by_day:
            by_day[day] = {"cost": 0, "sessions": 0, "tokens": 0}
        by_day[day]["cost"] += cost
        by_day[day]["sessions"] += 1
        by_day[day]["tokens"] += tokens

        # By week
        if s.get("date"):
            try:
                from datetime import datetime, timedelta
                d = datetime.strptime(s["date"], "%Y-%m-%d")
                week_start = d - timedelta(days=d.weekday())
                week_key = week_start.strftime("%Y-%m-%d")
                if week_key not in by_week:
                    by_week[week_key] = {"cost": 0, "sessions": 0}
                by_week[week_key]["cost"] += cost
                by_week[week_key]["sessions"] += 1
            except (ValueError, TypeError):
                pass

        proj = s.get("project_short") or s.get("project") or "unknown"
        if proj not in by_project:
            by_project[proj] = {"cost": 0, "sessions": 0, "tokens": 0}
        by_project[proj]["cost"] += cost
        by_project[proj]["sessions"] += 1
        by_project[proj]["tokens"] += tokens

        session_costs.append({"id": s["id"], "cost": cost, "project": proj, "date": s.get("date", "")})

    session_costs.sort(key=lambda x: x["cost"], reverse=True)

    if first_date and last_date:
        from datetime import datetime
        try:
            days = max(1, (datetime.strptime(last_date, "%Y-%m-%d") - datetime.strptime(first_date, "%Y-%m-%d")).days + 1)
        except ValueError:
            days = 1
    else:
        days = 1

    return {
        "totalCost": total_cost,
        "totalTokens": total_tokens,
        "totalInputTokens": total_input_tokens,
        "totalOutputTokens": total_output_tokens,
        "totalCacheReadTokens": total_cache_read_tokens,
        "totalCacheCreateTokens": total_cache_create_tokens,
        "avgContextPct": round(global_context_pct_sum / global_context_turn_count) if global_context_turn_count > 0 else 0,
        "dailyRate": total_cost / days,
        "firstDate": first_date,
        "lastDate": last_date,
        "days": days,
        "totalSessions": sessions_with_data,
        "byDay": by_day,
        "byWeek": by_week,
        "byProject": by_project,
        "topSessions": session_costs[:10],
        "byAgent": by_agent,
        "agentNoCostData": agent_no_cost_data,
    }
