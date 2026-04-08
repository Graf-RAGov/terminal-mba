"""Terminal detection, launch, and focus."""

import os
import subprocess
import sys
import shutil
import json


def detect_terminals() -> list[dict]:
    """Detect available terminal applications."""
    terminals = []
    platform = sys.platform

    if platform == "darwin":
        # iTerm2
        try:
            subprocess.run(
                ["osascript", "-e", 'application id "com.googlecode.iterm2"'],
                capture_output=True, timeout=3
            )
            terminals.append({"id": "iterm2", "name": "iTerm2", "available": True})
        except (subprocess.TimeoutExpired, OSError):
            terminals.append({"id": "iterm2", "name": "iTerm2", "available": False})

        # Terminal.app always available
        terminals.append({"id": "terminal", "name": "Terminal.app", "available": True})

        # Warp
        if os.path.exists("/Applications/Warp.app"):
            terminals.append({"id": "warp", "name": "Warp", "available": True})

        # Kitty
        if shutil.which("kitty"):
            terminals.append({"id": "kitty", "name": "Kitty", "available": True})

        # Alacritty
        if shutil.which("alacritty"):
            terminals.append({"id": "alacritty", "name": "Alacritty", "available": True})

        # cmux
        if os.path.exists("/Applications/cmux.app"):
            terminals.append({"id": "cmux", "name": "cmux", "available": True})

    elif platform == "linux":
        linux_terms = [
            {"id": "gnome-terminal", "name": "GNOME Terminal", "cmd": "gnome-terminal"},
            {"id": "konsole", "name": "Konsole", "cmd": "konsole"},
            {"id": "kitty", "name": "Kitty", "cmd": "kitty"},
            {"id": "alacritty", "name": "Alacritty", "cmd": "alacritty"},
            {"id": "xterm", "name": "xterm", "cmd": "xterm"},
        ]
        for t in linux_terms:
            available = shutil.which(t["cmd"]) is not None
            terminals.append({"id": t["id"], "name": t["name"], "available": available})

    else:  # Windows
        terminals.append({"id": "cmd", "name": "Command Prompt", "available": True})
        terminals.append({"id": "powershell", "name": "PowerShell", "available": True})
        if shutil.which("wt"):
            terminals.append({"id": "windows-terminal", "name": "Windows Terminal", "available": True})

    return terminals


def open_in_terminal(session_id: str, tool: str = "claude", flags: list[str] | None = None,
                     project_dir: str = "", terminal_id: str = "") -> None:
    """Open a session in a terminal."""
    flags = flags or []
    skip_perms = "skip-permissions" in flags

    if tool == "codex":
        cmd = f"codex resume {session_id}"
    else:
        cmd = f"claude --resume {session_id}"
        if skip_perms:
            cmd += " --dangerously-skip-permissions"

    cd_part = f"cd {json.dumps(project_dir)} && " if project_dir else ""
    full_cmd = cd_part + cmd
    escaped_cmd = full_cmd.replace('"', '\\"')

    platform = sys.platform

    if platform == "darwin":
        if terminal_id == "terminal":
            subprocess.run([
                "osascript", "-e",
                f'tell application "Terminal"\nactivate\ndo script "{escaped_cmd}"\nend tell'
            ], capture_output=True, timeout=5)
        elif terminal_id == "kitty":
            subprocess.Popen(["kitty", "--single-instance", "bash", "-c", f"{full_cmd}; exec bash"])
        elif terminal_id == "alacritty":
            subprocess.Popen(["alacritty", "-e", "bash", "-c", f"{full_cmd}; exec bash"])
        else:  # iterm2 or default
            script = f'''tell application "iTerm"
                activate
                set newWindow to (create window with default profile)
                tell current session of newWindow
                    write text "{escaped_cmd}"
                end tell
            end tell'''
            try:
                subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                subprocess.run([
                    "osascript", "-e",
                    f'tell application "Terminal" to do script "{escaped_cmd}"'
                ], capture_output=True, timeout=5)

    elif platform == "linux":
        if terminal_id == "kitty":
            subprocess.Popen(["kitty", "bash", "-c", f"{full_cmd}; exec bash"])
        elif terminal_id == "alacritty":
            subprocess.Popen(["alacritty", "-e", "bash", "-c", f"{full_cmd}; exec bash"])
        elif terminal_id == "konsole":
            subprocess.Popen(["konsole", "-e", "bash", "-c", f"{full_cmd}; exec bash"])
        elif terminal_id == "xterm":
            subprocess.Popen(["xterm", "-e", "bash", "-c", f"{full_cmd}; exec bash"])
        else:  # gnome-terminal
            subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"{full_cmd}; exec bash"])

    else:  # Windows
        if terminal_id == "powershell":
            subprocess.Popen(["start", "powershell", "-NoExit", "-Command", full_cmd], shell=True)
        elif terminal_id == "windows-terminal":
            subprocess.Popen(["wt", "new-tab", "cmd", "/k", full_cmd], shell=True)
        else:
            subprocess.Popen(["start", "cmd", "/k", full_cmd], shell=True)


def focus_terminal_by_pid(pid: int) -> dict:
    """Focus terminal window containing a process."""
    platform = sys.platform

    if platform == "darwin":
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "tty="],
                capture_output=True, text=True, timeout=2
            )
            tty = result.stdout.strip()
            if not tty:
                return {"ok": False}

            # Try iTerm2
            try:
                subprocess.run(
                    ["osascript", "-e", 'tell application "iTerm" to activate'],
                    capture_output=True, timeout=2
                )
                return {"ok": True, "terminal": "iTerm2"}
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Try Terminal.app
            try:
                subprocess.run(
                    ["osascript", "-e", 'tell application "Terminal" to activate'],
                    capture_output=True, timeout=2
                )
                return {"ok": True, "terminal": "Terminal.app"}
            except (subprocess.TimeoutExpired, OSError):
                pass
        except (subprocess.TimeoutExpired, OSError):
            pass

    return {"ok": False}
