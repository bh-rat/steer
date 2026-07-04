"""
Managed background processes for skills.

Skills that start dev servers or long-running helpers all hand-roll the
same fragile bash: spawn, poll a port, write a PID file, remember to
TERM-then-KILL. Steer owns that lifecycle:

    steer proc start web --ready-port 5173 -- npm run dev
    steer proc status web
    steer proc logs web
    steer proc stop web

Bookkeeping lives in ``<workspace>/.steer/proc/<name>/`` (pid, meta.json,
log). Steer only ever stops processes it started, and treats a recycled
PID (different executable) as stale rather than killable.
"""

import json
import os
import shlex
import signal
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import workspace_steer_dir


class ProcError(Exception):
    """A managed-process operation failed."""


def _proc_dir(name: str, workspace: str, create: bool = False) -> Path:
    from .paths import checked_path_component

    safe = checked_path_component(name, "process")
    path = workspace_steer_dir(workspace, create=create) / "proc" / safe
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _read_meta(directory: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _pid_matches(pid: int, expected_exe: str) -> bool:
    """Best-effort guard against recycled PIDs: reject zombies and
    processes whose command clearly differs from what we started.

    Case-insensitive on purpose: macOS framework Python re-execs as
    `.../Python.app/Contents/MacOS/Python` when argv[0] said
    `.../bin/python`.
    """
    try:
        proc = subprocess.run(
            ["ps", "-o", "state=,command=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True  # Can't check; assume it's ours
    output = proc.stdout.strip()
    if not output:
        return False  # ps has no record of the pid
    state, _, command = output.partition(" ")
    if state.startswith("Z"):
        return False  # defunct: still signalable, but not running
    command = command.strip()
    if not command:
        return True  # args unreadable; _pid_alive already vouched for it
    return Path(expected_exe).name.lower() in command.lower()


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def start(name: str, command: List[str], workspace: str = ".",
          ready_port: Optional[int] = None, ready_log: Optional[str] = None,
          timeout: float = 30.0, cwd: Optional[str] = None,
          env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Start a managed background process.

    Readiness: waits for `ready_port` to accept connections, or for
    `ready_log` (a substring) to appear in the log, or, with neither,
    just checks the process survives half a second.

    Returns a status dict; raises ProcError on failure (with log tail).
    """
    if not command:
        raise ProcError("No command given")
    existing = status(name, workspace)
    if existing.get("running"):
        raise ProcError(
            f"Process '{name}' is already running (pid {existing['pid']}). "
            f"Stop it first: steer proc stop {name}"
        )

    directory = _proc_dir(name, workspace, create=True)
    log_path = directory / "log"
    run_cwd = str(Path(cwd).expanduser()) if cwd else str(Path(workspace).expanduser())

    full_env = dict(os.environ)
    if env:
        full_env.update(env)

    with open(log_path, "ab") as log_file:
        log_file.write(
            f"\n--- steer proc start {datetime.now(timezone.utc).isoformat()} "
            f"--- {shlex.join(command)}\n".encode()
        )
        try:
            child = subprocess.Popen(
                command, cwd=run_cwd, env=full_env,
                stdout=log_file, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach: survive the parent shell
            )
        except OSError as exc:
            raise ProcError(f"Failed to start {command[0]!r}: {exc}") from exc

    meta = {
        "name": name,
        "pid": child.pid,
        "command": command,
        "cwd": run_cwd,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ready_port": ready_port,
        "owner_pid": os.getpid(),
    }
    (directory / "meta.json").write_text(json.dumps(meta, indent=2) + "\n",
                                         encoding="utf-8")

    # Readiness wait
    deadline = time.monotonic() + timeout
    ready = ready_port is None and ready_log is None
    while time.monotonic() < deadline:
        if child.poll() is not None:
            tail = logs(name, workspace, lines=15)
            raise ProcError(
                f"Process '{name}' exited immediately "
                f"(code {child.returncode}). Log tail:\n{tail}"
            )
        if ready_port is not None and _port_open(ready_port):
            ready = True
            break
        if ready_log is not None:
            try:
                if ready_log in log_path.read_text(encoding="utf-8", errors="replace"):
                    ready = True
                    break
            except OSError:
                pass
        if ready_port is None and ready_log is None:
            time.sleep(0.5)
            ready = child.poll() is None
            break
        time.sleep(0.25)

    if not ready:
        stop(name, workspace)
        tail = logs(name, workspace, lines=15)
        raise ProcError(
            f"Process '{name}' did not become ready within {timeout:.0f}s. "
            f"Stopped it. Log tail:\n{tail}"
        )
    return status(name, workspace)


def status(name: str, workspace: str = ".") -> Dict[str, Any]:
    """Status of one managed process."""
    directory = _proc_dir(name, workspace)
    meta = _read_meta(directory)
    if meta is None:
        return {"name": name, "running": False, "known": False}
    pid = int(meta.get("pid", 0))
    running = (
        pid > 0
        and _pid_alive(pid)
        and _pid_matches(pid, meta.get("command", ["?"])[0])
    )
    result = {
        "name": name,
        "known": True,
        "running": running,
        "pid": pid,
        "command": meta.get("command"),
        "started_at": meta.get("started_at"),
        "log": str(directory / "log"),
    }
    if meta.get("ready_port"):
        result["ready_port"] = meta["ready_port"]
        if running:
            result["port_open"] = _port_open(int(meta["ready_port"]))
    return result


def list_procs(workspace: str = ".") -> List[Dict[str, Any]]:
    """Status of every process steer knows about in this workspace."""
    base = workspace_steer_dir(workspace) / "proc"
    if not base.is_dir():
        return []
    return [status(child.name, workspace) for child in sorted(base.iterdir())
            if child.is_dir()]


def logs(name: str, workspace: str = ".", lines: int = 50) -> str:
    """Last N lines of a managed process's log."""
    log_path = _proc_dir(name, workspace) / "log"
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(content.splitlines()[-lines:])


def stop(name: str, workspace: str = ".", timeout: float = 5.0) -> Dict[str, Any]:
    """Stop a managed process: SIGTERM, wait, then SIGKILL."""
    info = status(name, workspace)
    if not info.get("known"):
        raise ProcError(f"Unknown process: '{name}'")
    if not info.get("running"):
        return {**info, "stopped": False, "reason": "not running"}

    pid = info["pid"]
    try:
        # The process group, so children (npm -> node) die too.
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return {**status(name, workspace), "stopped": True, "forced": False}
        time.sleep(0.2)

    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(0.2)
    return {**status(name, workspace), "stopped": True, "forced": True}
