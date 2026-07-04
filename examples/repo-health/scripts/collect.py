#!/usr/bin/env python3
"""Collect repository facts into out/health/data.json.

Agent contract (from steer's generated example.py): non-interactive,
single JSON envelope on stdout, diagnostics on stderr. Works with or
without git; stdlib only.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
             "dist", "build", "__pycache__", ".steer", "out", ".pytest_cache",
             ".mypy_cache", "target", ".next", ".tox",
             ".claude", ".agents"}  # installed skills are not *your* debt
MAX_TEXT_BYTES = 1_000_000
TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
TEST_HINTS = re.compile(r"(^test_.*\.py$)|(_test\.(py|go|rb)$)|"
                        r"(\.(test|spec)\.(js|jsx|ts|tsx|mjs)$)")


def _envelope(status, summary, data=None, artifacts=None):
    try:
        from steer.output import print_envelope
        return print_envelope(status, summary, data=data, artifacts=artifacts)
    except ImportError:
        result = {"status": status, "summary": summary}
        if data is not None:
            result["data"] = data
        if artifacts:
            result["artifacts"] = artifacts
        print(json.dumps(result, indent=2))
        return 0 if status != "error" else 1


def _git(args):
    try:
        proc = subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def git_activity():
    if _git(["rev-parse", "--is-inside-work-tree"]) != "true":
        return {"is_repo": False}
    log = _git(["log", "--since=30.days", "--pretty=%an"]) or ""
    authors = sorted({a for a in log.splitlines() if a})
    status = _git(["status", "--porcelain"]) or ""
    return {
        "is_repo": True,
        "commits_30d": len(log.splitlines()),
        "authors_30d": authors,
        "dirty_files": len([ln for ln in status.splitlines() if ln.strip()]),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
    }


def inventory(root: Path):
    by_ext, todos, test_files = {}, [], 0
    total_files = total_lines = 0
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        total_files += 1
        ext = path.suffix.lower() or "(none)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
        if TEST_HINTS.search(path.name):
            test_files += 1
        if path.stat().st_size > MAX_TEXT_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        total_lines += len(lines)
        for lineno, line in enumerate(lines, 1):
            if TODO_RE.search(line) and len(todos) < 50:
                todos.append({"file": str(path.relative_to(root)),
                              "line": lineno,
                              "text": line.strip()[:120]})
    top_ext = dict(sorted(by_ext.items(), key=lambda kv: -kv[1])[:8])
    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "by_extension": top_ext,
        "todos": todos,
        "test_files": test_files,
        "has_test_dir": any((root / d).is_dir()
                            for d in ("tests", "test", "__tests__", "spec")),
    }


def main() -> int:
    root = Path.cwd()
    data = {"workspace": str(root),
            "git": git_activity(),
            "inventory": inventory(root)}
    out = root / "out" / "health" / "data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    inv = data["inventory"]
    return _envelope(
        "ok",
        f"Collected {inv['total_files']} files, {len(inv['todos'])} debt "
        f"markers, {inv['test_files']} test files",
        data={"files": inv["total_files"], "todos": len(inv["todos"])},
        artifacts=[str(out.relative_to(root))],
    )


if __name__ == "__main__":
    sys.exit(main())
