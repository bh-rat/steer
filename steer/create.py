"""
Skill scaffolding: `steer new` generates a spec-compliant skill with the
chosen steer components wired into SKILL.md.

The templates encode what good skills hand-write: a trigger-
focused description shape, a context-gathering step 0, an agent↔human
credential handoff, flow enforcement prose backed by actual gating, and
scripts that follow the agentic-interface guidance (non-interactive,
JSON envelope on stdout, diagnostics on stderr).

Skills that use components get a bundled runtime (scripts/steer.py, see
vendor.py) holding exactly those components, and their SKILL.md invokes
it as `python3 scripts/steer.py ...`: running the skill needs Python,
not steer.
"""

import re
from pathlib import Path
from typing import Iterable, List, Optional, Set

from . import frontmatter
from .scaffold import FileSpec, ScaffoldResult, scaffold_project
from .vendor import COMPONENT_MODULES, RUNTIME_REL_PATH, generate, normalize_components

COMPONENTS = tuple(COMPONENT_MODULES)

# The templates below spell out vendor.RUNTIME_PROG ("python3
# scripts/steer.py") literally so they read as the prose an author will
# edit; test_vendor ties the two together and fails if they drift.

_DESCRIPTION_PLACEHOLDER = (
    "TODO: One sentence on what this skill does. "
    "Use when TODO: the user asks for X, mentions Y, or needs Z."
)

# User-invoked skills aren't triggered off the description, so it doesn't
# need trigger phrasing; it's what the human sees in the skill list.
_DESCRIPTION_PLACEHOLDER_USER_INVOKED = (
    "TODO: One sentence on what this skill does, shown to the human "
    "in the skill list."
)


_SECRET_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_STEP_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _skill_md(name: str, description: Optional[str], components: Set[str],
              license_name: Optional[str], author: Optional[str],
              scripts: bool, auto_learn: bool = False,
              user_invoked: bool = False, refs: bool = False,
              secret_keys: Optional[List[str]] = None) -> str:
    placeholder = (_DESCRIPTION_PLACEHOLDER_USER_INVOKED if user_invoked
                   else _DESCRIPTION_PLACEHOLDER)
    fm = {
        "name": name,
        "description": description or placeholder,
    }
    if user_invoked:
        # Claude Code: only the user can invoke this skill. Other clients
        # ignore the field and may still auto-trigger off the description.
        fm["disable-model-invocation"] = True
    if license_name:
        fm["license"] = license_name
    metadata = {"version": "0.1.0"}
    if author:
        metadata["author"] = author
    fm["metadata"] = metadata
    if auto_learn:
        # Claude Code skill-scoped hook: at every stop while this skill is
        # active, steer scans the transcript for corrections/failures and
        # (once) asks the agent to distill lessons before finishing.
        fm["hooks"] = {
            "Stop": [{
                "hooks": [{
                    "type": "command",
                    "command": f"steer learn reflect --skill {name}",
                    "timeout": 15,
                }],
            }],
        }

    parts: List[str] = [frontmatter.emit(fm)]
    parts.append(f"\n# {name}\n")
    parts.append(
        "TODO: One paragraph: what this skill accomplishes and the result "
        "the user gets.\n"
    )

    if components:
        parts.append(
            "\nThis skill bundles its own steer runtime at "
            "`scripts/steer.py`; the\ncommands below invoke it with "
            "`python3` and need nothing installed.\nPaths are relative to "
            "this skill's directory: when your working\ndirectory is "
            "elsewhere (it usually is), use the skill's full path\n"
            "(`python3 <path-to-this-skill>/scripts/steer.py ...`).\n"
        )

    setup_lines: List[str] = []
    if "context" in components:
        setup_lines.append(
            "1. **Ground yourself.** Run `python3 scripts/steer.py context` "
            "and read the snapshot before doing anything else; it tells you "
            "the platform, project type, git state, and which tools exist "
            "here."
        )
    if "learn" in components:
        setup_lines.append(
            f"{len(setup_lines) + 1}. **Apply past lessons.** Run "
            f"`python3 scripts/steer.py learn show` and follow what it says; "
            f"those lessons came from real previous runs."
        )
    if "secrets" in components:
        keys = secret_keys or [f"{name.upper().replace('-', '_')}_API_KEY"]
        if len(keys) == 1:
            check_cmds = f"`python3 scripts/steer.py secrets check {keys[0]}`"
            set_cmd = f"`python3 scripts/steer.py secrets set {keys[0]}`"
        else:
            check_cmds = ", ".join(
                f"`python3 scripts/steer.py secrets check {key}`"
                for key in keys)
            set_cmd = "`python3 scripts/steer.py secrets set <KEY>`"
        setup_lines.append(
            f"{len(setup_lines) + 1}. **Check credentials.** Run "
            f"{check_cmds}. If one is missing, ask the user to run "
            f"{set_cmd} (never ask them to paste the value into the chat), "
            f"then re-check."
        )
    if setup_lines:
        parts.append("\n## Before you start\n\n" + "\n".join(setup_lines) + "\n")

    if "flow" in components:
        parts.append(f"""
## Process

This skill has an enforced flow: steps verify themselves against
reality, and you cannot skip ahead.

1. Announce: "Working through the {name} flow."
2. Run `python3 scripts/steer.py flow status` (in the workspace) to see
   progress and the current step.
3. Do what the directive says. Steps with a verify condition complete
   automatically once reality matches; for mandate steps, mark completion
   with `python3 scripts/steer.py flow done <step-id>`.
4. Run `python3 scripts/steer.py flow next` and repeat until it reports
   all steps complete.

Do NOT claim the work is done while `python3 scripts/steer.py flow
status` shows incomplete steps. The flow is defined in `flow.toml`.
""")
    else:
        parts.append("""
## Steps

TODO: Numbered, concrete instructions. When a step uses a bundled file,
say explicitly whether to execute it ("Run: ...") or read it ("See: ...").
""")

    if "store" in components:
        parts.append("""
## Memory

This skill persists data between runs with the bundled `store` command
(per-skill SQLite). Examples:

    python3 scripts/steer.py store put last_run '"2026-06-11"'
    python3 scripts/steer.py store get last_run
    python3 scripts/steer.py store insert runs '{"file": "report.pdf", "ok": true}'

Use `--scope workspace` for state that belongs to this project rather
than the user.
""")

    if "proc" in components:
        parts.append("""
## Background processes

Start helpers through the bundled runtime so nothing leaks or zombies:

    python3 scripts/steer.py proc start dev --ready-port 5173 -- npm run dev
    python3 scripts/steer.py proc status dev
    python3 scripts/steer.py proc stop dev      # always stop what you started
""")

    if "learn" in components:
        auto_note = ""
        if auto_learn:
            auto_note = (
                "\nAuto-learning is on (Claude Code, needs the steer CLI "
                "installed): a Stop hook scans the session for corrections "
                "and failures and will prompt you to distill lessons if you "
                "forget. Other agents: follow the instructions below "
                "manually.\n"
            )
        parts.append(f"""
## Learning
{auto_note}
This skill improves with use. As you work:

- The moment the user corrects you, or something fails and then works a
  different way, capture it:
  `python3 scripts/steer.py learn note "<one imperative rule>" --kind correction`
  Lessons are atomic rules ("Use X not Y when Z"), never secrets.
- When a lesson from `python3 scripts/steer.py learn show` helped, run
  `python3 scripts/steer.py learn confirm <id>`; when one was wrong,
  `python3 scripts/steer.py learn dispute <id>`.
- Before finishing, record the outcome:
  `python3 scripts/steer.py learn run ok` (or `failed` with `--note`).

If a `learnings.md` exists in this skill, read it too; those are
promoted lessons that shipped with the skill.
""")

    if scripts:
        parts.append("""
## Output

Scripts print a single JSON result envelope to stdout
(`{"status", "summary", "data", "artifacts"}`); read `status` instead of
parsing prose. Diagnostics go to stderr.
""")

    if refs:
        parts.append("""
## References

Keep this file lean; put branch-only detail behind pointers so it loads
only when that branch is hit:

- TODO: "When doing X, first read the matching file under references/."
""")

    parts.append("""
## Gotchas

- TODO: Edge cases, failure modes, and what to do about them.
""")
    return "".join(parts)


_FLOW_HEADER = """\
# Declarative flow for this skill. The agent drives it with the bundled
# runtime, run inside the workspace:
#   python3 scripts/steer.py flow status | next | done <id>
#
# A step with [steps.verify] completes automatically when the condition
# holds (file_exists, dir_exists, glob, command, env). A step without
# verify is a mandate step: the agent marks it done explicitly.

name = "{name}"
"""

_FLOW_TOML = _FLOW_HEADER + """
[[steps]]
id = "prepare"
description = "TODO: first concrete action"
directive = "TODO: tell the agent exactly what to do, e.g. 'Create out/config.json with ...'"

[steps.verify]
file_exists = "out/config.json"

[[steps]]
id = "review"
description = "TODO: a judgment step the agent confirms explicitly"
directive = "TODO: what to check before marking done with `python3 {{skill_dir}}/scripts/steer.py flow done review`"
requires = ["prepare"]
"""


def _flow_toml(name: str, step_ids: Optional[List[str]]) -> str:
    """The flow.toml scaffold: the generic template, or a linear chain
    of the caller's named steps with TODO directives."""
    if not step_ids:
        return _FLOW_TOML.format(name=name)
    blocks = [_FLOW_HEADER.format(name=name)]
    previous = None
    for step_id in step_ids:
        lines = [
            "",
            "[[steps]]",
            f'id = "{step_id}"',
            f'description = "TODO: what \'{step_id}\' accomplishes"',
            f'directive = "TODO: tell the agent exactly what to do for \'{step_id}\'"',
        ]
        if previous:
            lines.append(f'requires = ["{previous}"]')
        lines += [
            "",
            "# Give this step a verify condition to complete automatically:",
            "# [steps.verify]",
            '# file_exists = "out/..."',
        ]
        blocks.append("\n".join(lines))
        previous = step_id
    return "\n".join(blocks) + "\n"


_EXAMPLE_SCRIPT = '''\
#!/usr/bin/env python3
"""Example skill script.

Agent contract: non-interactive, exits fast, single JSON envelope on
stdout, diagnostics on stderr. Run `--help` first instead of reading
the source.
"""
import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="world", help="Who to greet")
    args = parser.parse_args()

    # ... do the real work here ...
    print(json.dumps({
        "status": "ok",
        "summary": f"Greeted {args.name}",
        "data": {"name": args.name},
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def create_skill(name: str, parent_dir: str = ".",
                 description: Optional[str] = None,
                 components: Optional[Iterable[str]] = None,
                 scripts: bool = False, refs: bool = False,
                 license_name: Optional[str] = None,
                 author: Optional[str] = None,
                 auto_learn: bool = False,
                 user_invoked: bool = False,
                 secret_keys: Optional[Iterable[str]] = None,
                 flow_steps: Optional[Iterable[str]] = None) -> ScaffoldResult:
    """Scaffold a new skill directory. Returns the ScaffoldResult.

    auto_learn implies the learn component and adds a Claude-Code-only
    Stop hook to the frontmatter (steer learn reflect).

    user_invoked marks the skill as explicitly invoked by the human
    (disable-model-invocation: true, a Claude Code field; other clients
    may still auto-trigger).

    secret_keys (implies secrets) are the credential names wired into the
    generated check/set instructions; flow_steps (implies flow) become a
    linear chain of named steps in the generated flow.toml.

    Raises ValueError on a bad name or unknown component (callers get a
    clean message; deeper checks come from `steer validate`).
    """
    from .validate import NAME_MAX, NAME_PATTERN

    if not NAME_PATTERN.match(name) or len(name) > NAME_MAX:
        raise ValueError(
            f"Invalid skill name {name!r}: use lowercase letters, digits, and "
            f"single hyphens (max {NAME_MAX} chars), e.g. 'pdf-form-filler'"
        )
    chosen: Set[str] = set(components or [])
    if auto_learn:
        chosen.add("learn")
    secret_keys = list(secret_keys or [])
    flow_steps = list(flow_steps or [])
    for key in secret_keys:
        if not _SECRET_KEY_RE.match(key):
            raise ValueError(
                f"Invalid secret key {key!r}: use UPPER_SNAKE_CASE, "
                f"e.g. STRIPE_API_KEY"
            )
    for step_id in flow_steps:
        if not _STEP_ID_RE.match(step_id):
            raise ValueError(
                f"Invalid flow step id {step_id!r}: use lowercase "
                f"kebab-case, e.g. collect-data"
            )
    if len(set(flow_steps)) != len(flow_steps):
        raise ValueError("Duplicate flow step ids")
    if secret_keys:
        chosen.add("secrets")
    if flow_steps:
        chosen.add("flow")
    if chosen:
        normalize_components(chosen)  # unknown components raise here

    target = Path(parent_dir).expanduser() / name
    files = [FileSpec(
        "SKILL.md",
        _skill_md(name, description, chosen, license_name, author, scripts,
                  auto_learn=auto_learn, user_invoked=user_invoked, refs=refs,
                  secret_keys=secret_keys or None),
        "the skill entrypoint",
    )]
    if "flow" in chosen:
        files.append(FileSpec("flow.toml", _flow_toml(name, flow_steps or None),
                              "declarative flow definition"))
    if chosen:
        files.append(FileSpec(RUNTIME_REL_PATH.as_posix(), generate(chosen),
                              "bundled steer runtime (self-contained)"))
    dirs: List[str] = []
    if scripts:
        files.append(FileSpec("scripts/example.py", _EXAMPLE_SCRIPT,
                              "example script with the result envelope"))
    if refs:
        dirs.extend(["references", "assets"])

    result = scaffold_project(str(target), files=files, dirs=dirs)

    for spec in files:
        if spec.path.startswith("scripts/"):
            script = target / spec.path
            if script.exists():
                script.chmod(script.stat().st_mode | 0o755)
    return result
