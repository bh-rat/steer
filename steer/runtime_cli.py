"""
The runtime CLI core: skill resolution, output plumbing, and the
registry the per-component command modules (cli_secrets, cli_store,
cli_learn, cli_context, cli_flow, cli_proc) plug into.

Two entry points share these modules. The installed `steer` CLI imports
all of them (cli.py), and `steer new` copies this core plus exactly the
chosen components' modules into a skill's bundled runtime
(scripts/steer.py, see vendor.py), so installed skills run these
commands without steer on the machine and a subset bundle contains no
code for components it lacks.

VENDORED_SKILL_ROOT is the vendoring seam: None under the installed CLI;
the bundled runtime sets it to the directory of the skill it ships in,
which makes skill, flow, and version resolution positional (the file
knows where it lives) instead of inferred from --skill flags or the
working directory. Hints spell commands via output.CLI_HINT, which the
bundle rebinds the same way.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .output import output_json
from .paths import SKILL_ENV, infer_skill_name
from .skill import Skill, SkillNotFound

# Canonical component order: registration, --help, and bundle sections
# all follow it regardless of import order.
COMPONENT_ORDER = ("secrets", "store", "context", "flow", "proc", "learn")

# Vendoring seam (see module docstring).
VENDORED_SKILL_ROOT: Optional[Path] = None

# component name -> its argparse registrar; cli_<component> modules add
# themselves via @runtime_command when imported (or, in a bundle, when
# their amalgamated body runs).
RUNTIME_REGISTRARS: Dict[str, Callable] = {}


def runtime_command(name: str):
    """Register a component's CLI registrar under its component name."""

    def register(fn):
        RUNTIME_REGISTRARS[name] = fn
        return fn

    return register


def _err(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _emit(args, message: str, code: int = 0, **data) -> int:
    """One outcome, two audiences: a human line, or JSON with --json."""
    if getattr(args, "json", False):
        payload = {"ok": code == 0, **data, "message": message}
        output_json(payload)
    else:
        print(message)
    return code


def _vendored_skill_name() -> Optional[str]:
    if VENDORED_SKILL_ROOT is None:
        return None
    try:
        skill = Skill.load(VENDORED_SKILL_ROOT)
    except (OSError, SkillNotFound):
        return VENDORED_SKILL_ROOT.name
    return skill.name or VENDORED_SKILL_ROOT.name


def _resolve_skill(args, needed_for: str) -> Optional[str]:
    # A bundle's positional identity outranks STEER_SKILL: the env var
    # disambiguates when steer can't tell which skill is meant, but this
    # file ships inside one; an inherited env var must not redirect its
    # secrets/store/lessons to another skill. Deliberately not
    # infer_skill_name(start=VENDORED_SKILL_ROOT) either: with the
    # bundle's own SKILL.md gone that would walk UP and adopt an
    # enclosing skill's name, while _vendored_skill_name falls back to
    # the directory name and can't cross the skill boundary.
    name = (getattr(args, "skill", None)
            or _vendored_skill_name()
            or os.environ.get(SKILL_ENV)
            or infer_skill_name())
    if not name:
        _err(
            f"Could not determine which skill {needed_for} belongs to. "
            f"Pass --skill <name>, set STEER_SKILL, or run from inside a "
            f"skill directory."
        )
        return None
    return name


def register_runtime_commands(sub, components=None) -> None:
    """Register runtime subcommands; components=None means all registered."""
    for name in COMPONENT_ORDER:
        registrar = RUNTIME_REGISTRARS.get(name)
        if registrar is None:
            continue
        if components is not None and name not in components:
            continue
        registrar(sub)


def runtime_main(argv: Optional[List[str]] = None,
                 components: Optional[List[str]] = None,
                 prog: str = "steer",
                 version: Optional[str] = None) -> int:
    """Entry point for a bundled runtime: only runtime commands, no authoring."""
    included = [c for c in COMPONENT_ORDER
                if c in RUNTIME_REGISTRARS
                and (components is None or c in components)]
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"Steer runtime bundled with this skill. "
                    f"Components: {', '.join(included)}.",
    )
    if version:
        parser.add_argument("--version", action="version",
                            version=f"{prog} (steer runtime) {version}")
    sub = parser.add_subparsers(dest="command", required=True)
    register_runtime_commands(sub, included)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        # Steer raises ValueError for user-fixable input problems
        # (bad skill/flow/process names, bad scopes): print, don't trace.
        return _err(str(exc))
    except KeyboardInterrupt:
        return 130
