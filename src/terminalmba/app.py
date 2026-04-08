"""FastAPI application with all API routes."""

import logging
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import orjson

logger = logging.getLogger(__name__)

from . import __version__
from .data import (
    load_sessions, load_session_detail, delete_session,
    get_session_preview, get_session_replay, export_session_markdown,
    get_git_commits, get_project_git_info,
)
from .search import search_full_text
from .cost import compute_session_cost, get_cost_analytics
from .active import get_active_sessions
from .terminals import detect_terminals, open_in_terminal, focus_terminal_by_pid
from .convert import convert_session
from .handoff import generate_handoff
from .changelog import CHANGELOG


class ORJSONResponse(JSONResponse):
    """Fast JSON response using orjson."""
    media_type = "application/json"

    def render(self, content) -> bytes:
        return orjson.dumps(content)


app = FastAPI(title="TerminalMBA", version=__version__, default_response_class=ORJSONResponse)

# ── CORS ──────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3847", "http://127.0.0.1:3847"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_LOCALHOST_HOSTS = {"localhost", "127.0.0.1"}


@app.middleware("http")
async def check_origin_for_mutations(request: Request, call_next):
    """Block cross-origin mutating requests (POST/DELETE) from non-localhost origins."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in _LOCALHOST_HOSTS:
                return ORJSONResponse({"error": "Forbidden origin"}, status_code=403)
    return await call_next(request)


# ── Frontend serving ───────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"
FRONTEND_SRC_DIR = Path(__file__).parent.parent.parent / "frontend" / "src"


def _get_frontend_html() -> str:
    """Get the frontend HTML, trying dist first, then src."""
    for base_dir in [FRONTEND_DIR, FRONTEND_SRC_DIR]:
        index = base_dir / "index.html"
        if index.exists():
            return index.read_text(encoding="utf-8")
    return "<html><body><h1>TerminalMBA</h1><p>Frontend not built. Run: cd frontend && bun run build</p></body></html>"


# ── Static routes ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return _get_frontend_html()


@app.get("/favicon.ico")
async def favicon():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#60a5fa"/><path d="M8 8l8 4 8-4v16l-8 4-8-4z" fill="none" stroke="#fff" stroke-width="2"/></svg>'
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/manifest.json")
async def manifest():
    for base_dir in [FRONTEND_DIR, FRONTEND_SRC_DIR]:
        mf = base_dir / "manifest.json"
        if mf.exists():
            return Response(content=mf.read_text(encoding="utf-8"), media_type="application/json")
    return ORJSONResponse({"name": "terminalmba"}, status_code=200)


# ── Sessions API ───────────────────────────────────────────

@app.get("/api/sessions")
async def api_sessions():
    return load_sessions()


@app.get("/api/session/{session_id}/export")
async def api_session_export(session_id: str, project: str = ""):
    md = export_session_markdown(session_id, project)
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="session-{session_id[:8]}.md"'},
    )


@app.get("/api/session/{session_id}")
async def api_session_detail(session_id: str, project: str = ""):
    return load_session_detail(session_id, project)


@app.get("/api/preview/{session_id}")
async def api_session_preview(session_id: str, project: str = "", limit: int = 10):
    return get_session_preview(session_id, project, limit)


@app.get("/api/replay/{session_id}")
async def api_session_replay(session_id: str, project: str = ""):
    return get_session_replay(session_id, project)


@app.get("/api/cost/{session_id}")
async def api_session_cost(session_id: str, project: str = ""):
    return compute_session_cost(session_id, project)


@app.delete("/api/session/{session_id}")
async def api_delete_session(session_id: str, request: Request):
    try:
        body = await request.json()
        project = body.get("project", "")
    except Exception:
        project = ""
    deleted = delete_session(session_id, project)
    return {"ok": True, "deleted": deleted}


# ── Search ─────────────────────────────────────────────────

@app.get("/api/search")
async def api_search(q: str = ""):
    sessions = load_sessions()
    return search_full_text(q, sessions)


# ── Analytics ──────────────────────────────────────────────

@app.get("/api/analytics/cost")
async def api_cost_analytics(request: Request):
    sessions = load_sessions()
    params = request.query_params
    from_date = params.get("from")
    to_date = params.get("to")
    if from_date:
        sessions = [s for s in sessions if s.get("date", "") >= from_date]
    if to_date:
        sessions = [s for s in sessions if s.get("date", "") <= to_date]
    return get_cost_analytics(sessions)


# ── Active sessions ────────────────────────────────────────

@app.get("/api/active")
async def api_active():
    return get_active_sessions()


# ── Terminals ──────────────────────────────────────────────

@app.get("/api/terminals")
async def api_terminals():
    return detect_terminals()


# ── Launch ─────────────────────────────────────────────────

@app.post("/api/launch")
async def api_launch(request: Request):
    try:
        body = await request.json()
        open_in_terminal(
            body.get("sessionId", ""),
            body.get("tool", "claude"),
            body.get("flags", []),
            body.get("project", ""),
            body.get("terminal", ""),
        )
        return {"ok": True}
    except Exception as e:
        logger.exception("launch failed")
        return ORJSONResponse({"ok": False, "error": "Operation failed"}, status_code=400)


# ── Focus ──────────────────────────────────────────────────

@app.post("/api/focus")
async def api_focus(request: Request):
    try:
        body = await request.json()
        result = focus_terminal_by_pid(body.get("pid", 0))
        return result
    except Exception as e:
        logger.exception("focus failed")
        return ORJSONResponse({"ok": False, "error": "Operation failed"}, status_code=400)


# ── Open IDE ───────────────────────────────────────────────

@app.post("/api/open-ide")
async def api_open_ide(request: Request):
    try:
        body = await request.json()
        ide = body.get("ide", "")
        project = body.get("project", "")
        target = project
        if ".." in (target or ""):
            return ORJSONResponse({"ok": False, "error": "Invalid path"}, status_code=400)
        if target and os.path.exists(target) and not os.path.isdir(target):
            target = os.path.dirname(target)
        if target and not os.path.isdir(target):
            return ORJSONResponse({"ok": False, "error": "Directory not found"}, status_code=400)
        if ide == "cursor":
            subprocess.Popen(["cursor", target or "."])
        elif ide == "code":
            subprocess.Popen(["code", target or "."])
        return {"ok": True}
    except Exception as e:
        logger.exception("open-ide failed")
        return ORJSONResponse({"ok": False, "error": "Operation failed"}, status_code=400)


# ── Git commits ────────────────────────────────────────────

@app.get("/api/git-commits")
async def api_git_commits(project: str = "", request: Request = None):
    import time
    params = request.query_params if request else {}
    from_ts = int(params.get("from", "0") or "0")
    to_ts = int(params.get("to", str(int(time.time() * 1000))) or str(int(time.time() * 1000)))
    return get_git_commits(project, from_ts, to_ts)


# ── Git info ───────────────────────────────────────────────

@app.get("/api/git-info")
async def api_git_info(project: str = ""):
    info = get_project_git_info(project)
    return info or {"error": "No git repo found"}


# ── Handoff ────────────────────────────────────────────────

@app.get("/api/handoff/{session_id}")
async def api_handoff(session_id: str, project: str = "", verbosity: str = "standard"):
    result = generate_handoff(session_id, project, {"verbosity": verbosity})
    if result.get("ok"):
        return Response(
            content=result["markdown"],
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="handoff-{session_id[:8]}.md"'},
        )
    return ORJSONResponse(result, status_code=404)


# ── Convert ────────────────────────────────────────────────

@app.post("/api/convert")
async def api_convert(request: Request):
    try:
        body = await request.json()
        result = convert_session(
            body.get("sessionId", ""),
            body.get("project", ""),
            body.get("targetFormat", ""),
        )
        return result
    except Exception as e:
        logger.exception("convert failed")
        return ORJSONResponse({"ok": False, "error": "Operation failed"}, status_code=400)


# ── Bulk Delete ────────────────────────────────────────────

@app.post("/api/bulk-delete")
async def api_bulk_delete(request: Request):
    try:
        body = await request.json()
        results = []
        for s in body.get("sessions", []):
            deleted = delete_session(s.get("id", ""), s.get("project", ""))
            results.append({"id": s.get("id", ""), "deleted": deleted})
        return {"ok": True, "results": results}
    except Exception as e:
        logger.exception("bulk-delete failed")
        return ORJSONResponse({"ok": False, "error": "Operation failed"}, status_code=400)


# ── Version ────────────────────────────────────────────────

@app.get("/api/version")
async def api_version():
    current = __version__
    latest = None
    update_available = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"https://pypi.org/pypi/terminalmba/json")
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("info", {}).get("version")
                if latest and latest != current:
                    update_available = _is_newer(latest, current)
    except Exception:
        pass
    return {"current": current, "latest": latest, "updateAvailable": update_available}


def _is_newer(latest: str, current: str) -> bool:
    """Check if latest version is newer than current."""
    try:
        l_parts = [int(x) for x in latest.split(".")]
        c_parts = [int(x) for x in current.split(".")]
        for i in range(3):
            lv = l_parts[i] if i < len(l_parts) else 0
            cv = c_parts[i] if i < len(c_parts) else 0
            if lv > cv:
                return True
            if lv < cv:
                return False
    except (ValueError, IndexError):
        pass
    return False


# ── Remotes ────────────────────────────────────────────────

@app.get("/api/remotes")
async def api_remotes():
    from .remote import get_remotes_status
    return get_remotes_status()


@app.post("/api/remotes/pull")
async def api_remotes_pull():
    from .remote import pull_all_remotes
    global _sessions_cache, _sessions_cache_ts
    results = pull_all_remotes()
    # Invalidate session cache so next fetch includes remote data
    from .data import _sessions_cache as sc
    from . import data as data_mod
    data_mod._sessions_cache = None
    data_mod._sessions_cache_ts = 0
    return results


@app.post("/api/remotes/pull/{name}")
async def api_remotes_pull_one(name: str):
    from .remote import get_remote, pull_remote
    from . import data as data_mod
    remote = get_remote(name)
    if not remote:
        return ORJSONResponse({"error": f"Remote '{name}' not found"}, status_code=404)
    result = pull_remote(remote)
    data_mod._sessions_cache = None
    data_mod._sessions_cache_ts = 0
    return result


# ── Changelog ──────────────────────────────────────────────

@app.get("/api/changelog")
async def api_changelog():
    return CHANGELOG


# ── Mount static files for frontend dist ───────────────────

_assets_dir = FRONTEND_DIR / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
