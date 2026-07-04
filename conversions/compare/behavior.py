#!/usr/bin/env python3
"""Behavior comparison: original skills vs their steer rebuilds.

Five reproducible checks, no LLM involved:

  T1  server child leaked on cleanup      (webapp-testing)
  T2  chatty server stalls the pipe       (webapp-testing)
  T3  startup failure diagnostics         (webapp-testing)
  T4  phase gates actually gate           (systematic-debugging)
  T5  credential handling                 (vercel-cli-with-tokens)

Usage:
  python3 behavior.py --originals <dir with anthropic-skills/ superpowers/ vercel-agent-skills/>
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
CONVERSIONS = HERE.parent
STEER = os.environ.get("STEER_BIN", "steer")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def kill_quietly(pid: int) -> None:
    try:
        os.kill(pid, 15)
    except OSError:
        pass


def run(cmd, timeout=120, env=None, cwd=None):
    merged = dict(os.environ)
    if env:
        merged.update(env)
    started = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, env=merged, cwd=cwd)
    return proc, time.monotonic() - started


def t1_orphaned_child(with_server: Path, tmp: Path):
    """Cleanup kills the wrapper it spawned; does the server child survive?"""
    facts = {}

    port = free_port()
    pidfile = tmp / "child1.pid"
    proc, _ = run([sys.executable, str(with_server),
                   "--server", f"{sys.executable} {FIXTURES}/dev_server.py {port}",
                   "--port", str(port), "--timeout", "20",
                   "--", sys.executable, "-c", "print('automation ran')"],
                  env={"DEV_SERVER_PIDFILE": str(pidfile)})
    child = int(pidfile.read_text()) if pidfile.exists() else 0
    time.sleep(0.5)
    facts["original"] = {
        "exit_code": proc.returncode,
        "child_alive_after_cleanup": bool(child and pid_alive(child)),
        "port_still_bound": port_open(port),
    }
    if child:
        kill_quietly(child)

    port = free_port()
    pidfile = tmp / "child2.pid"
    ws = tmp / "t1-ws"
    ws.mkdir()
    proc, _ = run([STEER, "proc", "start", "dev", "--ready-port", str(port),
                   "--workspace", str(ws),
                   "--", sys.executable, f"{FIXTURES}/dev_server.py", str(port)],
                  env={"DEV_SERVER_PIDFILE": str(pidfile)})
    started_ok = proc.returncode == 0
    proc, _ = run([STEER, "proc", "stop", "dev", "--workspace", str(ws)])
    child = int(pidfile.read_text()) if pidfile.exists() else 0
    time.sleep(0.5)
    facts["steer"] = {
        "start_ok": started_ok,
        "stop_ok": proc.returncode == 0,
        "child_alive_after_stop": bool(child and pid_alive(child)),
        "port_still_bound": port_open(port),
    }
    if child:
        kill_quietly(child)
    return facts


def t2_chatty_pipe(with_server: Path, tmp: Path):
    """Verbose startup output: pipe with no reader vs log file."""
    facts = {}

    port = free_port()
    proc, secs = run([sys.executable, str(with_server),
                      "--server", f"{sys.executable} {FIXTURES}/chatty_server.py {port}",
                      "--port", str(port), "--timeout", "10",
                      "--", sys.executable, "-c", "print('automation ran')"])
    facts["original"] = {
        "exit_code": proc.returncode,
        "reported": "failed to start" in (proc.stdout + proc.stderr).lower(),
        "seconds": round(secs, 1),
    }

    port = free_port()
    ws = tmp / "t2-ws"
    ws.mkdir()
    proc, secs = run([STEER, "proc", "start", "chat", "--ready-port", str(port),
                      "--timeout", "10", "--workspace", str(ws),
                      "--", sys.executable, f"{FIXTURES}/chatty_server.py", str(port)])
    facts["steer"] = {
        "exit_code": proc.returncode,
        "became_ready": proc.returncode == 0 and port_open(port),
        "seconds": round(secs, 1),
    }
    run([STEER, "proc", "stop", "chat", "--workspace", str(ws)])
    return facts


def t3_startup_diagnostics(with_server: Path, tmp: Path):
    """Server dies at startup: does the error reach the caller?"""
    facts = {}

    port = free_port()
    proc, secs = run([sys.executable, str(with_server),
                      "--server", f"{sys.executable} {FIXTURES}/failing_server.py {port}",
                      "--port", str(port), "--timeout", "6",
                      "--", sys.executable, "-c", "print('automation ran')"])
    out = proc.stdout + proc.stderr
    facts["original"] = {
        "exit_code": proc.returncode,
        "cause_in_output": "DATABASE_URL" in out,
        "seconds": round(secs, 1),
    }

    port = free_port()
    ws = tmp / "t3-ws"
    ws.mkdir()
    proc, secs = run([STEER, "proc", "start", "bad", "--ready-port", str(port),
                      "--timeout", "6", "--workspace", str(ws),
                      "--", sys.executable, f"{FIXTURES}/failing_server.py", str(port)])
    out = proc.stdout + proc.stderr
    facts["steer"] = {
        "exit_code": proc.returncode,
        "cause_in_output": "DATABASE_URL" in out,
        "seconds": round(secs, 1),
    }
    return facts


def t4_flow_gates(tmp: Path):
    """The Iron Law as machinery: fix stays locked until artifacts exist."""
    ws = tmp / "t4-ws"
    ws.mkdir()
    run([STEER, "install", str(CONVERSIONS / "systematic-debugging"),
         "--dest", str(ws / ".claude" / "skills")])
    env = {"STEER_SKILL": "systematic-debugging"}
    flow_file = ws / ".claude" / "skills" / "systematic-debugging" / "flow.toml"
    base = [STEER, "flow", "--file", str(flow_file)] if flow_file.exists() else \
           [STEER, "flow"]

    def flow(*args):
        return run(base[:2] + list(args) + base[2:], env=env, cwd=str(ws))[0]

    premature = flow("done", "fix")
    facts = {"premature_fix_refused": premature.returncode != 0
             or "not ready" in (premature.stdout + premature.stderr).lower()
             or "blocked" in (premature.stdout + premature.stderr).lower()}

    progression = []
    for artifact in ["evidence.md", "comparison.md", "hypothesis.md",
                     "failing-test.md"]:
        status = flow("status", "--json")
        try:
            current = json.loads(status.stdout)["progress"].get("current_step")
        except (ValueError, KeyError):
            current = None
        progression.append(current)
        (ws / "out" / "debug").mkdir(parents=True, exist_ok=True)
        (ws / "out" / "debug" / artifact).write_text("recorded\n",
                                                     encoding="utf-8")

    final_done = flow("done", "fix")
    status = flow("status", "--json")
    try:
        completed = json.loads(status.stdout)["progress"].get("completed_steps")
    except (ValueError, KeyError):
        completed = None
    facts["steps_unlocked_in_order"] = progression == [
        "investigate", "analyze", "hypothesize", "failing-test"]
    facts["progression_seen"] = progression
    facts["fix_done_after_artifacts"] = final_done.returncode == 0
    facts["completed_steps"] = completed
    facts["original_equivalent"] = "prose only; nothing refuses a premature fix"
    return facts


def t5_credentials(originals: Path, tmp: Path):
    """Missing-secret handoff, and whether discovery leaks the value."""
    home = tmp / "steer-home"
    home.mkdir()
    env = {"STEER_HOME": str(home)}
    env_missing = dict(env)

    check = run([STEER, "secrets", "check", "VERCEL_TOKEN",
                 "--skill", "vercel-cli-with-tokens"], env=env_missing)[0]
    out = check.stdout + check.stderr
    facts = {"steer": {
        "missing_is_actionable": "steer secrets set" in out,
        "missing_exit_code": check.returncode,
    }}

    env_present = dict(env, VERCEL_TOKEN="vca_fake_not_a_real_token")
    check = run([STEER, "secrets", "check", "VERCEL_TOKEN",
                 "--skill", "vercel-cli-with-tokens"], env=env_present)[0]
    facts["steer"]["env_var_found"] = check.returncode == 0
    facts["steer"]["value_in_output"] = "vca_fake_not_a_real_token" in (
        check.stdout + check.stderr)

    dotenv_dir = tmp / "t5-proj"
    dotenv_dir.mkdir()
    secret = "vca_secret_LEAKCANARY"
    (dotenv_dir / ".env").write_text(f"MY_VERCEL_KEY={secret}\n",
                                     encoding="utf-8")
    original_cmd = run(["sh", "-c", "grep -i 'vercel' .env 2>/dev/null"],
                       cwd=str(dotenv_dir))[0]
    steered_cmd = run(["sh", "-c",
                       "grep -o '^[A-Za-z_]*VERCEL[A-Za-z_]*=' .env 2>/dev/null"],
                      cwd=str(dotenv_dir))[0]
    facts["original"] = {
        "discovery_command": "grep -i 'vercel' .env",
        "value_reaches_transcript": secret in original_cmd.stdout,
    }
    facts["steer"]["names_only_discovery"] = (
        "MY_VERCEL_KEY=" in steered_cmd.stdout
        and secret not in steered_cmd.stdout)
    return facts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", required=True, type=Path,
                        help="Directory containing clones of anthropic-skills, "
                             "superpowers, vercel-agent-skills")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    with_server = (args.originals / "anthropic-skills" / "skills" /
                   "webapp-testing" / "scripts" / "with_server.py")
    if not with_server.is_file():
        print(f"missing {with_server}", file=sys.stderr)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="steer-compare-"))
    try:
        results = {
            "t1_orphaned_child": t1_orphaned_child(with_server, tmp),
            "t2_chatty_pipe": t2_chatty_pipe(with_server, tmp),
            "t3_startup_diagnostics": t3_startup_diagnostics(with_server, tmp),
            "t4_flow_gates": t4_flow_gates(tmp),
            "t5_credentials": t5_credentials(args.originals, tmp),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
