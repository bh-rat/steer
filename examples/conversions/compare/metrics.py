#!/usr/bin/env python3
"""Static comparison: original skills vs their steer rebuilds.

For each pair: what enters context on trigger (SKILL.md body), what ships
in the directory (files, script lines), what is deferred behind pointers
(references), what is dead weight (files nothing mentions), and what
`steer validate` finds.

Usage:
  python3 metrics.py --originals <dir with anthropic-skills/ superpowers/ vercel-agent-skills/>
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONVERSIONS = HERE.parent
STEER = os.environ.get("STEER_BIN", "steer")

SCRIPT_EXTS = {".py", ".sh", ".mjs", ".cjs", ".js", ".rb", ".ts"}
TEXT_EXTS = {".md", ".mdx", ".txt", ".toml", ".py", ".sh", ".ts", ".js"}
SKIP_NAMES = {"SKILL.md", "LICENSE.txt", "LICENSE", "NOTICE.md", ".DS_Store"}


def body_of(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2]
    return text


def est_tokens(text: str) -> int:
    return len(text) // 4


def unreferenced(skill_dir: Path, files: list) -> list:
    corpus = ""
    for f in files:
        if f.suffix.lower() in TEXT_EXTS or f.name == "SKILL.md":
            corpus += f.read_text(encoding="utf-8", errors="replace")
    dead = []
    for f in files:
        if f.name in SKIP_NAMES:
            continue
        others = corpus.replace(f.read_text(encoding="utf-8", errors="replace")
                                if f.suffix.lower() in TEXT_EXTS else "", "", 1)
        if f.name not in others:
            dead.append(str(f.relative_to(skill_dir)))
    return dead


def measure(skill_dir: Path) -> dict:
    files = [f for f in sorted(skill_dir.rglob("*"))
             if f.is_file() and f.name != ".DS_Store"
             and ".git" not in f.relative_to(skill_dir).parts]
    skill_md = skill_dir / "SKILL.md"
    body = body_of(skill_md)
    scripts_loc = sum(
        len(f.read_text(encoding="utf-8", errors="replace").splitlines())
        for f in files if f.suffix.lower() in SCRIPT_EXTS)
    ref_files = [f for f in files
                 if "references" in f.parts or "examples" in f.parts]
    ref_tokens = sum(
        est_tokens(f.read_text(encoding="utf-8", errors="replace"))
        for f in ref_files)

    validate = subprocess.run([STEER, "validate", str(skill_dir), "--json"],
                              capture_output=True, text=True)
    findings = {"error": 0, "warning": 0, "info": 0}
    try:
        for f in json.loads(validate.stdout)["findings"]:
            findings[f["level"]] += 1
    except (ValueError, KeyError):
        pass

    return {
        "files": len(files),
        "body_lines": len(body.splitlines()),
        "body_tokens_est": est_tokens(body),
        "shipped_script_lines": scripts_loc,
        "deferred_reference_files": len(ref_files),
        "deferred_reference_tokens_est": ref_tokens,
        "files_nothing_references": unreferenced(skill_dir, files),
        "validate": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", required=True, type=Path)
    args = parser.parse_args()

    pairs = {
        "webapp-testing": args.originals / "anthropic-skills" / "skills" / "webapp-testing",
        "systematic-debugging": args.originals / "superpowers" / "skills" / "systematic-debugging",
        "vercel-cli-with-tokens": args.originals / "vercel-agent-skills" / "skills" / "vercel-cli-with-tokens",
        "humanizer": args.originals / "humanizer",
    }
    results = {}
    for name, original in pairs.items():
        if not original.is_dir():
            print(f"missing {original}", file=sys.stderr)
            return 2
        results[name] = {
            "original": measure(original),
            "steer": measure(CONVERSIONS / name),
        }
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
