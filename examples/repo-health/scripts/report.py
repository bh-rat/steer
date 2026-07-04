#!/usr/bin/env python3
"""Render out/health/data.json into out/health/REPORT.md.

Records this run's totals in steer's workspace store (imported from the
bundled runtime next to this script) and shows trends when a previous
run exists. Degrades gracefully when that import fails (report still
renders, no trend).
"""
import json
import sys
from datetime import date
from pathlib import Path


def _envelope(status, summary, data=None, artifacts=None, errors=None):
    try:
        from steer.output import print_envelope
        return print_envelope(status, summary, data=data,
                              artifacts=artifacts, errors=errors)
    except ImportError:
        result = {"status": status, "summary": summary}
        if data is not None:
            result["data"] = data
        if artifacts:
            result["artifacts"] = artifacts
        if errors:
            result["errors"] = errors
        print(json.dumps(result, indent=2))
        return 0 if status != "error" else 1


def _trend(totals):
    """Trend lines vs the previous run, via the workspace store."""
    try:
        from steer import Store
    except ImportError:
        return ["- trend unavailable (bundled runtime scripts/steer.py "
                "is missing)"]
    with Store("repo-health", scope="workspace") as store:
        previous = store.get("last_totals")
        store.put("last_totals", totals)
    if not isinstance(previous, dict):
        return ["- first recorded run; trends start next time"]
    lines = []
    for key, label in (("files", "files"), ("lines", "lines of text"),
                       ("todos", "debt markers"), ("test_files", "test files")):
        before, now = previous.get(key), totals[key]
        if not isinstance(before, int):
            continue
        arrow = "→" if now == before else ("↑" if now > before else "↓")
        lines.append(f"- {label}: {before} {arrow} {now}")
    return lines


def main() -> int:
    root = Path.cwd()
    data_path = root / "out" / "health" / "data.json"
    if not data_path.is_file():
        return _envelope("error", "out/health/data.json missing",
                         errors=["Run: python3 scripts/collect.py first"])
    data = json.loads(data_path.read_text(encoding="utf-8"))
    git, inv = data["git"], data["inventory"]

    totals = {"files": inv["total_files"], "lines": inv["total_lines"],
              "todos": len(inv["todos"]), "test_files": inv["test_files"]}
    trend_lines = _trend(totals)

    if git.get("is_repo"):
        authors = ", ".join(git["authors_30d"]) or "none"
        activity = [
            f"- {git['commits_30d']} commits in the last 30 days "
            f"(branch `{git['branch']}`)",
            f"- authors: {authors}",
            f"- uncommitted changes: {git['dirty_files']} files",
        ]
    else:
        activity = ["- not a git repository"]

    ext_lines = [f"- `{ext}`: {count}"
                 for ext, count in inv["by_extension"].items()]
    todo_lines = [f"- `{t['file']}:{t['line']}`: {t['text']}"
                  for t in inv["todos"][:10]]
    if len(inv["todos"]) > 10:
        todo_lines.append(f"- …and {len(inv['todos']) - 10} more "
                          f"(full list in data.json)")

    tests = (f"- {inv['test_files']} test files; test directory "
             f"{'present' if inv['has_test_dir'] else 'absent'}")

    report = "\n".join([
        f"# Repository health: {date.today().isoformat()}",
        "",
        f"Workspace: `{data['workspace']}`",
        "",
        "## Activity", *activity,
        "",
        "## Inventory",
        f"- {inv['total_files']} files, {inv['total_lines']} lines of text",
        *ext_lines,
        "",
        "## Marked debt", *(todo_lines or ["- none found"]),
        "",
        "## Tests", tests,
        "",
        "## Trend", *trend_lines,
        "",
    ])
    out = root / "out" / "health" / "REPORT.md"
    out.write_text(report, encoding="utf-8")
    return _envelope("ok",
                     f"Report written ({totals['todos']} debt markers, "
                     f"{totals['test_files']} test files)",
                     data=totals,
                     artifacts=[str(out.relative_to(root))])


if __name__ == "__main__":
    sys.exit(main())
