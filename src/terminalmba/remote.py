"""Remote session sync for TerminalMBA."""

import gzip
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import orjson

TERMINALMBA_DIR = Path.home() / ".terminalmba"
REMOTES_CONFIG = TERMINALMBA_DIR / "remotes.json"
REMOTES_CACHE_DIR = TERMINALMBA_DIR / "remotes"
KEYS_DIR = TERMINALMBA_DIR / "keys"


def _ensure_dirs() -> None:
    TERMINALMBA_DIR.mkdir(exist_ok=True)
    REMOTES_CACHE_DIR.mkdir(exist_ok=True)
    KEYS_DIR.mkdir(mode=0o700, exist_ok=True)


def get_hostname() -> str:
    return socket.gethostname().split(".")[0]


# ── Config ────────────────────────────────────────────────


def load_remotes_config() -> list[dict]:
    if not REMOTES_CONFIG.exists():
        return []
    try:
        data = orjson.loads(REMOTES_CONFIG.read_bytes())
        return data.get("remotes", [])
    except Exception:
        return []


def save_remotes_config(remotes: list[dict]) -> None:
    _ensure_dirs()
    REMOTES_CONFIG.write_bytes(orjson.dumps({"remotes": remotes}, option=orjson.OPT_INDENT_2))


def get_remote(name: str) -> dict | None:
    for r in load_remotes_config():
        if r["name"] == name:
            return r
    return None


# ── Sync export (runs on remote) ─────────────────────────


def sync_export() -> bytes:
    """Export all local sessions as gzipped JSON. Called via SSH."""
    from .data import load_sessions
    hostname = get_hostname()
    sessions = load_sessions()
    payload = {"hostname": hostname, "timestamp": time.time(), "sessions": sessions}
    raw = orjson.dumps(payload)
    return gzip.compress(raw)


# ── Pull (runs on local) ─────────────────────────────────


def pull_remote(remote: dict) -> dict:
    """SSH to remote, run sync-export, decompress, cache."""
    name = remote["name"]
    host = remote["host"]
    key_file = KEYS_DIR / name

    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]
    if key_file.exists():
        ssh_cmd += ["-i", str(key_file)]
    ssh_cmd += [host, "bash", "-lc", "terminalmba sync-export"]

    try:
        result = subprocess.run(ssh_cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            return {"ok": False, "error": f"SSH failed: {stderr}", "name": name}

        raw = gzip.decompress(result.stdout)
        payload = orjson.loads(raw)

        # Cache to disk
        _ensure_dirs()
        cache_file = REMOTES_CACHE_DIR / f"{name}.json.gz"
        cache_file.write_bytes(result.stdout)

        sessions = payload.get("sessions", [])
        hostname = payload.get("hostname", name)

        # Tag sessions with host info
        for s in sessions:
            s["host"] = hostname
            s["remote"] = True

        return {
            "ok": True,
            "name": name,
            "hostname": hostname,
            "sessions": len(sessions),
            "timestamp": time.time(),
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "SSH timeout (30s)", "name": name}
    except Exception as e:
        return {"ok": False, "error": str(e), "name": name}


def pull_all_remotes() -> list[dict]:
    """Pull from all configured remotes."""
    results = []
    for remote in load_remotes_config():
        results.append(pull_remote(remote))
    return results


# ── Cache reading ─────────────────────────────────────────


def load_cached_remote(name: str) -> tuple[list[dict], float | None]:
    """Load cached remote sessions. Returns (sessions, cache_mtime)."""
    cache_file = REMOTES_CACHE_DIR / f"{name}.json.gz"
    if not cache_file.exists():
        return [], None
    try:
        raw = gzip.decompress(cache_file.read_bytes())
        payload = orjson.loads(raw)
        hostname = payload.get("hostname", name)
        sessions = payload.get("sessions", [])
        for s in sessions:
            s["host"] = hostname
            s["remote"] = True
        return sessions, cache_file.stat().st_mtime
    except Exception:
        return [], None


def load_all_cached_remotes() -> list[dict]:
    """Load sessions from all cached remotes."""
    all_sessions: list[dict] = []
    for remote in load_remotes_config():
        sessions, _ = load_cached_remote(remote["name"])
        all_sessions.extend(sessions)
    return all_sessions


def get_remotes_status() -> list[dict]:
    """Get status of all remotes with last sync info."""
    result = []
    for remote in load_remotes_config():
        cache_file = REMOTES_CACHE_DIR / f"{remote['name']}.json.gz"
        last_sync = None
        session_count = 0
        if cache_file.exists():
            last_sync = cache_file.stat().st_mtime
            try:
                raw = gzip.decompress(cache_file.read_bytes())
                payload = orjson.loads(raw)
                session_count = len(payload.get("sessions", []))
            except Exception:
                pass
        result.append({
            "name": remote["name"],
            "host": remote["host"],
            "lastSync": last_sync,
            "sessions": session_count,
        })
    return result


# ── SSH key setup ─────────────────────────────────────────


def generate_key(name: str) -> str:
    """Generate ed25519 keypair for a remote. Returns public key."""
    _ensure_dirs()
    key_file = KEYS_DIR / name
    if key_file.exists():
        return (KEYS_DIR / f"{name}.pub").read_text().strip()

    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_file), "-N", "", "-C", f"terminalmba-sync-{name}"],
        check=True, capture_output=True,
    )
    return (KEYS_DIR / f"{name}.pub").read_text().strip()


def ensure_remote_setup(host: str) -> dict:
    """Ensure uv and terminalmba are installed on remote."""
    install_script = (
        'export PATH="$HOME/.local/bin:$PATH" && '
        '(command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh) && '
        'uv tool install "terminalmba @ git+https://github.com/Graf-RAGov/terminal-mba.git" --force 2>&1 || true'
    )
    try:
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=accept-new", host, "bash", "-c", json.dumps(install_script)],
            capture_output=True, timeout=120,
        )
        return {"ok": True, "output": result.stdout.decode(errors="replace")}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Install timeout (120s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def install_key_on_remote(host: str, public_key: str) -> dict:
    """Install restricted key on remote's authorized_keys."""
    # Build the restricted authorized_keys entry
    forced_command = 'command="bash -lc \'terminalmba sync-export\'",no-port-forwarding,no-X11-forwarding,no-agent-forwarding'
    entry = f'{forced_command} {public_key}'

    # Use ssh to append to authorized_keys
    script = f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo {json.dumps(entry)} >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'

    try:
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=accept-new", host, "bash", "-c", json.dumps(script)],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            return {"ok": False, "error": f"Failed to install key: {stderr}"}
        return {"ok": True}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "SSH timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def remove_remote(name: str) -> None:
    """Remove remote config, key, and cache."""
    remotes = load_remotes_config()
    remotes = [r for r in remotes if r["name"] != name]
    save_remotes_config(remotes)

    # Remove key files
    for ext in ("", ".pub"):
        kf = KEYS_DIR / f"{name}{ext}"
        if kf.exists():
            kf.unlink()

    # Remove cache
    cache_file = REMOTES_CACHE_DIR / f"{name}.json.gz"
    if cache_file.exists():
        cache_file.unlink()
