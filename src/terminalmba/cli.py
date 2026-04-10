"""Typer CLI for TerminalMBA."""

import os
import signal
import subprocess
import sys
import webbrowser
from typing import Optional

import typer

from . import __version__

app = typer.Typer(name="terminalmba", help="AI coding agent session dashboard (Python fork of codedash)")

DEFAULT_PORT = 3847
DEFAULT_HOST = "localhost"


@app.command()
def run(
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="Server port"),
    host: str = typer.Option(DEFAULT_HOST, "--host", "-h", help="Bind address"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
):
    """Start the dashboard server."""
    import uvicorn
    typer.echo("")
    typer.echo("  \033[36m\033[1mTerminalMBA\033[0m -- AI Sessions Dashboard")
    typer.echo(f"  \033[2mhttp://{host}:{port}\033[0m")
    typer.echo("  \033[2mPress Ctrl+C to stop\033[0m")
    typer.echo("")

    if not no_browser:
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    bind_addr = "127.0.0.1" if host == "localhost" else host
    uvicorn.run("terminalmba.app:app", host=bind_addr, port=port, log_level="warning")


@app.command("list")
def list_sessions(
    limit: int = typer.Argument(20, help="Number of sessions to show"),
):
    """List sessions in terminal."""
    from .data import load_sessions
    sessions = load_sessions()
    projects = {s.get("project", "") for s in sessions}
    typer.echo(f"\n  \033[36m\033[1m{len(sessions)} sessions\033[0m across {len(projects)} projects\n")

    for s in sessions[:limit]:
        tool_color = "\033[36m" if s.get("tool") == "codex" else "\033[34m"
        tool = f"{tool_color}{s.get('tool', '')}\033[0m"
        msg = (s.get("first_message", "") or "")[:50].ljust(50)
        proj = s.get("project_short", "")
        sid = s.get("id", "")[:12]
        last_time = s.get("last_time", "")
        typer.echo(f"  {tool}  {sid}  {last_time}  {msg}  \033[2m{proj}\033[0m")

    if len(sessions) > limit:
        typer.echo(f"\n  \033[2m... and {len(sessions) - limit} more (terminalmba list {limit + 20})\033[0m")
    typer.echo("")


@app.command()
def stats():
    """Show session statistics."""
    from .data import load_sessions
    sessions = load_sessions()
    projects: dict = {}
    for s in sessions:
        p = s.get("project_short") or "unknown"
        if p not in projects:
            projects[p] = {"count": 0, "messages": 0}
        projects[p]["count"] += 1
        projects[p]["messages"] += s.get("messages", 0)

    typer.echo(f"\n  \033[36m\033[1mSession Stats\033[0m\n")
    typer.echo(f"  Total sessions:  {len(sessions)}")
    typer.echo(f"  Total projects:  {len(projects)}")
    for tool in ("claude", "codex", "opencode", "cursor", "kiro", "claude-ext"):
        count = sum(1 for s in sessions if s.get("tool") == tool)
        if count > 0:
            typer.echo(f"  {tool} sessions: {count}")

    typer.echo(f"\n  \033[1mTop projects:\033[0m")
    sorted_projects = sorted(projects.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
    for name, info in sorted_projects:
        typer.echo(f"    {str(info['count']).rjust(3)} sessions  {name}")
    typer.echo("")


@app.command()
def search(query: str = typer.Argument(..., help="Search query")):
    """Search across all session messages."""
    from .data import load_sessions
    from .search import search_full_text
    sessions = load_sessions()
    results = search_full_text(query, sessions)

    if not results:
        typer.echo(f'\n  No results for "{query}"\n')
        return

    typer.echo(f'\n  \033[36m\033[1m{len(results)} sessions\033[0m matching "{query}"\n')
    for r in results[:15]:
        s = next((x for x in sessions if x["id"] == r["sessionId"]), None)
        proj = s.get("project_short", "") if s else ""
        tool = s.get("tool", "?") if s else "?"
        date = s.get("last_time", "") if s else ""
        typer.echo(f"  \033[1m{r['sessionId'][:12]}\033[0m  {tool}  {date}  \033[2m{proj}\033[0m")
        for m in r["matches"][:2]:
            role = "\033[34mYOU\033[0m" if m["role"] == "user" else "\033[32mAI \033[0m"
            snippet = m["snippet"].replace("\n", " ")[:100]
            typer.echo(f"    {role} {snippet}")

    if len(results) > 15:
        typer.echo(f"\n  \033[2m... and {len(results) - 15} more\033[0m")
    typer.echo("")


@app.command()
def show(session_id: str = typer.Argument(..., help="Session ID (full or prefix)")):
    """Show session details + messages."""
    from .data import load_sessions, get_session_preview
    from .cost import compute_session_cost
    sessions = load_sessions()
    session = next(
        (s for s in sessions if s["id"] == session_id or s["id"].startswith(session_id)),
        None,
    )
    if not session:
        typer.echo(f"  Session not found: {session_id}", err=True)
        raise typer.Exit(code=1)

    preview = get_session_preview(session["id"], session.get("project", ""), 20)
    cost = compute_session_cost(session["id"], session.get("project", ""))

    typer.echo("")
    typer.echo(f"  \033[36m\033[1mSession {session['id']}\033[0m")
    typer.echo(f"  Tool:    {session.get('tool', '')}")
    typer.echo(f"  Project: {session.get('project_short', '') or session.get('project', '') or 'unknown'}")
    typer.echo(f"  Started: {session.get('first_time', '')}")
    typer.echo(f"  Last:    {session.get('last_time', '')}")
    typer.echo(f"  Msgs:    {session.get('messages', 0)} inputs, {session.get('detail_messages', 0)} total")
    if cost["cost"] > 0:
        typer.echo(f"  Cost:    ${cost['cost']:.2f} ({cost.get('model', '') or 'unknown'})")
        typer.echo(f"  Tokens:  {cost['inputTokens']//1000}K in / {cost['outputTokens']//1000}K out")
    typer.echo("")

    if preview:
        typer.echo("  \033[1mConversation:\033[0m")
        for m in preview:
            role = "\033[34mYOU\033[0m" if m["role"] == "user" else "\033[32mAI \033[0m"
            text = m.get("content", "").replace("\n", " ")[:120]
            typer.echo(f"  {role} {text}")
        typer.echo("")

    resume_cmd = "codex resume" if session.get("tool") == "codex" else "claude --resume"
    typer.echo(f"  Resume: \033[2m{resume_cmd} {session['id']}\033[0m")
    typer.echo("")


@app.command()
def handoff(
    session_id: str = typer.Argument(..., help="Session ID or tool name for quick handoff"),
    target: str = typer.Argument("any", help="Target agent (claude, codex, any)"),
    verbosity: str = typer.Option("standard", help="Verbosity level"),
    out: str = typer.Option("", help="Output file path"),
):
    """Generate handoff document."""
    from .data import load_sessions
    from .handoff import generate_handoff, quick_handoff

    if session_id in ("claude", "codex", "opencode"):
        result = quick_handoff(session_id, target, {"verbosity": verbosity})
    else:
        sessions = load_sessions()
        match = next(
            (s for s in sessions if s["id"] == session_id or s["id"].startswith(session_id)),
            None,
        )
        if not match:
            typer.echo(f"  Session not found: {session_id}", err=True)
            raise typer.Exit(code=1)
        result = generate_handoff(match["id"], match.get("project", ""), {"verbosity": verbosity, "target": target})

    if not result.get("ok"):
        typer.echo(f"  \033[31mError:\033[0m {result.get('error', '')}\n", err=True)
        raise typer.Exit(code=1)

    if out:
        with open(out, "w") as f:
            f.write(result["markdown"])
        typer.echo(f"\n  \033[32mHandoff saved to {out}\033[0m")
        typer.echo(f"  Source: {result['session']['tool']} ({result['session']['id'][:12]})")
        typer.echo(f"  Messages: {result['session']['messages']}\n")
    else:
        typer.echo(result["markdown"])


@app.command("convert")
def convert_cmd(
    session_id: str = typer.Argument(..., help="Session ID"),
    target_format: str = typer.Argument(..., help="Target format (claude/codex)"),
):
    """Convert session between agents."""
    from .data import load_sessions
    from .convert import convert_session
    sessions = load_sessions()
    match = next(
        (s for s in sessions if s["id"] == session_id or s["id"].startswith(session_id)),
        None,
    )
    if not match:
        typer.echo(f"  Session not found: {session_id}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n  Converting {match.get('tool', '')} session \033[1m{match['id'][:12]}\033[0m -> {target_format}...")
    result = convert_session(match["id"], match.get("project", ""), target_format)

    if not result.get("ok"):
        typer.echo(f"  \033[31mError:\033[0m {result.get('error', '')}\n", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"  \033[32mDone!\033[0m")
    typer.echo(f"  New session: {result['target']['sessionId']}")
    typer.echo(f"  Messages:    {result['target']['messages']}")
    typer.echo(f"  File:        {result['target']['file']}")
    typer.echo(f"  Resume:      \033[2m{result['target']['resumeCmd']}\033[0m\n")


@app.command("export")
def export_cmd(
    output: str = typer.Argument("", help="Output file path (default: terminalmba-export-DATE.tar.gz)"),
):
    """Export all sessions to archive."""
    if not output:
        from datetime import date
        output = f"terminalmba-export-{date.today().isoformat()}.tar.gz"
    typer.echo(f"\n  Exporting to {output}...")
    typer.echo("  \033[33mExport not yet implemented in Python version\033[0m\n")


@app.command("import")
def import_cmd(
    archive: str = typer.Argument(..., help="Archive file path"),
):
    """Import sessions from archive."""
    typer.echo(f"\n  Importing from {archive}...")
    typer.echo("  \033[33mImport not yet implemented in Python version\033[0m\n")


@app.command()
def update():
    """Check for updates."""
    typer.echo("\n  \033[36m\033[1mChecking for updates...\033[0m\n")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "terminalmba"], check=True)
        typer.echo(f"\n  \033[32mUpdated!\033[0m Run \033[2mterminalmba restart\033[0m to apply.\n")
    except subprocess.CalledProcessError:
        typer.echo("  \033[31mUpdate failed.\033[0m Try: pip install --upgrade terminalmba\n")


@app.command()
def restart(
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Server port"),
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Bind address"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
):
    """Restart the server."""
    typer.echo(f"\n  Stopping TerminalMBA on port {port}...")
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, timeout=5, text=True,
        )
        if result.stdout.strip():
            for pid_str in result.stdout.strip().split("\n"):
                pid_str = pid_str.strip()
                if pid_str.isdigit():
                    os.kill(int(pid_str), signal.SIGKILL)
        typer.echo("  Stopped.")
    except Exception:
        typer.echo("  No running instance found.")

    import time
    time.sleep(0.5)
    typer.echo("  Starting...\n")
    run(port=port, host=host, no_browser=no_browser)


@app.command()
def stop(
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Server port"),
):
    """Stop the server."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, timeout=5, text=True,
        )
        if result.stdout.strip():
            for pid_str in result.stdout.strip().split("\n"):
                pid_str = pid_str.strip()
                if pid_str.isdigit():
                    os.kill(int(pid_str), signal.SIGKILL)
            typer.echo(f"\n  TerminalMBA stopped (port {port})\n")
        else:
            typer.echo(f"\n  No TerminalMBA running on port {port}\n")
    except Exception:
        typer.echo(f"\n  No TerminalMBA running on port {port}\n")


@app.command()
def version():
    """Show version."""
    typer.echo(__version__)


# ── Sync Export (called via SSH) ──────────────────────────


@app.command("sync-export", hidden=True)
def sync_export_cmd():
    """Export sessions as gzipped JSON to stdout (for remote sync)."""
    from .remote import sync_export
    sys.stdout.buffer.write(sync_export())


# ── Remote Subcommands ────────────────────────────────────

remote_app = typer.Typer(name="remote", help="Manage remote session sources")
app.add_typer(remote_app)


@remote_app.command("add")
def remote_add(
    host: str = typer.Argument(..., help="SSH host (e.g. vadim@192.168.1.198)"),
    name: str = typer.Option("", "--name", "-n", help="Friendly name (default: derived from host)"),
):
    """Add a remote and set up SSH key access."""
    from .remote import (
        _validate_name, ensure_remote_setup, generate_key, get_remote,
        install_key_on_remote, load_remotes_config, pull_remote,
        save_remotes_config,
    )

    if not name:
        name = host.split("@")[-1].replace(".", "-")

    # Sanitize auto-generated or user-provided name
    import re
    name = re.sub(r'[^a-zA-Z0-9_-]', '-', name)
    _validate_name(name)

    if get_remote(name):
        typer.echo(f"\n  Remote '{name}' already exists. Remove it first.\n")
        raise typer.Exit(code=1)

    typer.echo(f"\n  \033[36m\033[1mAdding remote '{name}'\033[0m ({host})\n")

    # Step 1: Install uv + terminalmba on remote
    typer.echo("  1. Installing uv + terminalmba on remote...")
    typer.echo(f"     \033[2m(you may be prompted for password)\033[0m")
    setup = ensure_remote_setup(host)
    if setup["ok"]:
        typer.echo(f"     \033[32mDone\033[0m")
    else:
        typer.echo(f"     \033[33mWarning:\033[0m {setup['error']}")
        typer.echo(f"     Continuing — ensure terminalmba is installed on remote manually.")

    # Step 2: Generate key
    typer.echo("  2. Generating SSH key...")
    public_key = generate_key(name)
    typer.echo(f"     \033[32mDone\033[0m")

    # Step 3: Install restricted key on remote
    typer.echo("  3. Installing restricted key on remote...")
    typer.echo(f"     \033[2m(you may be prompted for password)\033[0m")
    result = install_key_on_remote(host, public_key)
    if not result["ok"]:
        typer.echo(f"     \033[31mFailed:\033[0m {result['error']}")
        typer.echo(f"\n  Manual setup: copy this to remote ~/.ssh/authorized_keys:")
        typer.echo(f'  restrict,command="export PATH=$HOME/.local/bin:$PATH && terminalmba sync-export" {public_key}\n')
        # Still save the config so user can fix manually
        remotes = load_remotes_config()
        remotes.append({"name": name, "host": host})
        save_remotes_config(remotes)
        raise typer.Exit(code=1)
    typer.echo(f"     \033[32mDone\033[0m")

    # Step 4: Save config
    typer.echo("  4. Saving config...")
    remotes = load_remotes_config()
    remotes.append({"name": name, "host": host})
    save_remotes_config(remotes)
    typer.echo(f"     \033[32mDone\033[0m")

    # Step 5: Test
    typer.echo("  5. Testing connection...")
    remote = {"name": name, "host": host}
    test_result = pull_remote(remote)
    if test_result["ok"]:
        typer.echo(f"     \033[32mSuccess!\033[0m {test_result['sessions']} sessions from {test_result.get('hostname', name)}")
    else:
        typer.echo(f"     \033[33mWarning:\033[0m {test_result['error']}")
        typer.echo(f"     Remote saved but sync failed. Check that terminalmba is installed on remote.")

    typer.echo(f"\n  \033[32mRemote '{name}' added.\033[0m")
    typer.echo(f"  Sync:   terminalmba remote pull {name}")
    typer.echo(f"  Test:   terminalmba remote test {name}")
    typer.echo(f"  Remove: terminalmba remote remove {name}\n")


@remote_app.command("list")
def remote_list():
    """List configured remotes."""
    from .remote import get_remotes_status
    remotes = get_remotes_status()
    if not remotes:
        typer.echo("\n  No remotes configured. Add one with: terminalmba remote add user@host\n")
        return

    typer.echo(f"\n  \033[36m\033[1m{len(remotes)} remotes\033[0m\n")
    for r in remotes:
        sync_info = ""
        if r["lastSync"]:
            from datetime import datetime
            dt = datetime.fromtimestamp(r["lastSync"])
            sync_info = f"  last sync: {dt.strftime('%Y-%m-%d %H:%M')}  ({r['sessions']} sessions)"
        else:
            sync_info = "  \033[2mnever synced\033[0m"
        typer.echo(f"  \033[1m{r['name']}\033[0m  {r['host']}{sync_info}")
    typer.echo("")


@remote_app.command("test")
def remote_test(
    name: str = typer.Argument(..., help="Remote name"),
):
    """Test connectivity to a remote."""
    from .remote import get_remote, pull_remote
    remote = get_remote(name)
    if not remote:
        typer.echo(f"\n  Remote '{name}' not found.\n")
        raise typer.Exit(code=1)

    typer.echo(f"\n  Testing '{name}' ({remote['host']})...")
    result = pull_remote(remote)
    if result["ok"]:
        typer.echo(f"  \033[32mSuccess!\033[0m {result['sessions']} sessions from {result.get('hostname', name)}\n")
    else:
        typer.echo(f"  \033[31mFailed:\033[0m {result['error']}\n")
        raise typer.Exit(code=1)


@remote_app.command("pull")
def remote_pull(
    name: str = typer.Argument("", help="Remote name (all if omitted)"),
):
    """Pull sessions from remote(s)."""
    from .remote import get_remote, load_remotes_config, pull_all_remotes, pull_remote

    if name:
        remote = get_remote(name)
        if not remote:
            typer.echo(f"\n  Remote '{name}' not found.\n")
            raise typer.Exit(code=1)
        typer.echo(f"\n  Pulling from '{name}'...")
        result = pull_remote(remote)
        if result["ok"]:
            typer.echo(f"  \033[32mDone!\033[0m {result['sessions']} sessions\n")
        else:
            typer.echo(f"  \033[31mFailed:\033[0m {result['error']}\n")
    else:
        remotes = load_remotes_config()
        if not remotes:
            typer.echo("\n  No remotes configured.\n")
            return
        typer.echo(f"\n  Pulling from {len(remotes)} remotes...")
        results = pull_all_remotes()
        for r in results:
            status = f"\033[32m{r['sessions']} sessions\033[0m" if r["ok"] else f"\033[31m{r['error']}\033[0m"
            typer.echo(f"  {r['name']}: {status}")
        typer.echo("")


@remote_app.command("remove")
def remote_remove(
    name: str = typer.Argument(..., help="Remote name"),
):
    """Remove a remote."""
    from .remote import get_remote, remove_remote
    remote = get_remote(name)
    if not remote:
        typer.echo(f"\n  Remote '{name}' not found.\n")
        raise typer.Exit(code=1)

    remove_remote(name)
    typer.echo(f"\n  \033[32mRemote '{name}' removed.\033[0m\n")


if __name__ == "__main__":
    app()
