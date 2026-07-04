"""
The steer CLI.

Author-time:  steer new | validate | package | install | list | bundle
Runtime:      steer secrets | store | learn | context | flow | proc

The runtime commands live in runtime_cli.py, which `steer new` also
copies into each skill's bundled runtime (scripts/steer.py) so installed
skills run them without steer on the machine. Every runtime command
resolves its skill from --skill, the STEER_SKILL env var, or the nearest
SKILL.md above the working directory. Errors are written for agents:
they say what to run next.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .output import output_json
from .runtime_cli import _err, register_runtime_commands


def _csv(raw: str) -> List[str]:
    return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]


# -- new --------------------------------------------------------------


def _cmd_new(args) -> int:
    from .create import create_skill
    from .validate import summarize, validate_skill

    components = _csv(args.with_components)
    try:
        result = create_skill(
            args.name, parent_dir=args.dir, description=args.description,
            components=components, scripts=args.scripts, refs=args.refs,
            license_name=args.license, author=args.author,
            auto_learn=args.auto_learn, user_invoked=args.user_invoked,
            secret_keys=_csv(args.secret_keys),
            flow_steps=_csv(args.flow_steps),
        )
    except ValueError as exc:
        return _err(str(exc))

    skill_dir = Path(args.dir).expanduser() / args.name
    print(f"Created skill at {skill_dir}")
    for created in result.created:
        print(f"  + {created}")
    for skipped in result.skipped:
        print(f"  = {skipped} (already existed, kept)")

    has_flow = "flow" in components or bool(args.flow_steps)
    findings = validate_skill(skill_dir)
    print(f"\nValidation: {summarize(findings)}")
    print("\nNext steps:")
    print(f"  1. Edit {skill_dir}/SKILL.md: replace every TODO, starting with the description")
    if has_flow:
        print(f"  2. Define real steps in {skill_dir}/flow.toml")
    print(f"  {'3' if has_flow else '2'}. Check it: steer validate {skill_dir}")
    print(f"  {'4' if has_flow else '3'}. Try it: steer install {skill_dir}")
    return 0


# -- validate / package / install / list / bundle ------------------------


def _resolve_skill_path(path_arg: Optional[str]) -> Path:
    if path_arg:
        return Path(path_arg).expanduser()
    from .paths import find_skill_root

    root = find_skill_root(".")
    return root if root else Path(".")


def _cmd_validate(args) -> int:
    from .validate import has_errors, summarize, validate_skill

    path = _resolve_skill_path(args.path)
    findings = validate_skill(path, for_packaging=args.packaging)
    if args.json:
        output_json({
            "path": str(path),
            "findings": [
                {"level": f.level, "code": f.code, "message": f.message}
                for f in findings
            ],
            "errors": sum(1 for f in findings if f.level == "error"),
            "ok": not has_errors(findings),
        })
    else:
        if not findings:
            print(f"✓ {path}: clean")
        else:
            print(f"{path}: {summarize(findings)}")
            for f in findings:
                icon = {"error": "✗", "warning": "⚠", "info": "·"}[f.level]
                print(f"  {icon} {f.code}: {f.message}")
    return 1 if has_errors(findings) else 0


def _cmd_package(args) -> int:
    from .distribute import DistributeError, package_skill
    from .skill import SkillNotFound
    from .vendor import read_runtime_header, write_runtime

    path = _resolve_skill_path(args.path)
    # A stale bundle (written by another steer version) is mechanical
    # drift in a generated file: refresh it to this version's output.
    # An edited bundle is a deliberate change; packaging refuses it
    # instead (RUNTIME_EDITED escalates to an error).
    header = read_runtime_header(path)
    if header is not None and header.version != __version__:
        try:
            write_runtime(path, header.components)
        except ValueError as exc:
            return _err(f"can't refresh bundled runtime: {exc}")
        print(f"↻ Refreshed bundled runtime (steer {header.version} → "
              f"{__version__})")
    try:
        out = package_skill(path, out=args.output)
    except (DistributeError, SkillNotFound) as exc:
        return _err(str(exc))
    size_kb = out.stat().st_size / 1024
    print(f"✓ Packaged {out} ({size_kb:.0f} KB)")
    print("  Upload to the Claude API (POST /v1/skills), claude.ai Settings → "
          "Capabilities, or install locally: steer install " + str(out))
    return 0


def _cmd_install(args) -> int:
    from .distribute import DistributeError, install_skill
    from .skill import SkillNotFound

    scope = "user" if args.user else "project"
    try:
        target = install_skill(args.source, scope=scope,
                               dest_root=args.dest, force=args.force)
    except (DistributeError, SkillNotFound) as exc:
        return _err(str(exc))
    print(f"✓ Installed to {target}")
    return 0


def _cmd_list(args) -> int:
    from .skill import discover
    from .validate import validate_skill
    from .distribute import validation_summary_line

    skills = discover()
    if args.json:
        output_json([
            {
                "name": s.name or s.dir_name,
                "description": s.description,
                "version": s.version,
                "path": str(s.path),
            }
            for s in skills
        ])
        return 0
    if not skills:
        print("No skills found in .claude/skills, .agents/skills (project or user).")
        print("Create one: steer new my-skill")
        return 0
    for s in skills:
        findings = validate_skill(s.path)
        status = validation_summary_line(findings)
        desc = (s.description[:70] + "…") if len(s.description) > 70 else s.description
        version = f" v{s.version}" if s.version else ""
        print(f"{s.name or s.dir_name}{version}  [{status}]")
        print(f"  {desc}")
        print(f"  {s.path}")
    return 0


def _cmd_bundle(args) -> int:
    from .skill import Skill, SkillNotFound
    from .vendor import read_runtime_header, write_runtime

    path = _resolve_skill_path(args.path)
    try:
        skill = Skill.load(path)
    except SkillNotFound as exc:
        return _err(str(exc))

    components: Optional[List[str]] = None
    if args.with_components:
        components = _csv(args.with_components)
    else:
        header = read_runtime_header(skill.path)
        if header is not None:
            components = header.components
    if not components:
        return _err(
            "No components given and no bundled runtime to read them from. "
            "Pass --with, e.g.: steer bundle --with secrets,store"
        )
    try:
        target = write_runtime(skill.path, components)
    except ValueError as exc:
        return _err(str(exc))
    print(f"✓ Bundled runtime at {target} "
          f"(steer {__version__}; components: {', '.join(components)})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steer",
        description="The framework for building Agent Skills: scaffolding, "
                    "validation, packaging, and runtime components (secrets, "
                    "store, context, flow, proc, learn).",
    )
    parser.add_argument("--version", action="version",
                        version=f"steer {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # new
    p_new = sub.add_parser("new", help="Scaffold a new skill")
    p_new.add_argument("name", help="Skill name (lowercase-kebab-case)")
    p_new.add_argument("--dir", default=".", help="Parent directory (default: .)")
    p_new.add_argument("--description", help="Skill description (what + when to use)")
    p_new.add_argument("--with", dest="with_components", default="",
                       help="Components to wire in: "
                            "secrets,store,context,flow,proc,learn")
    p_new.add_argument("--secrets", dest="secret_keys", default="",
                       metavar="KEY[,KEY...]",
                       help="Credential names to wire into the generated "
                            "instructions, e.g. STRIPE_API_KEY (implies the "
                            "secrets component)")
    p_new.add_argument("--steps", dest="flow_steps", default="",
                       metavar="ID[,ID...]",
                       help="Flow step ids to generate as a linear chain in "
                            "flow.toml, e.g. collect,report,review (implies "
                            "the flow component)")
    p_new.add_argument("--auto-learn", action="store_true",
                       help="Wire a Claude Code Stop hook that auto-prompts "
                            "lesson capture (implies learn; Claude-Code-only; "
                            "the hook itself needs steer installed)")
    p_new.add_argument("--user-invoked", action="store_true",
                       help="Only the user invokes this skill; sets "
                            "disable-model-invocation: true (Claude Code; "
                            "other clients may still auto-trigger)")
    p_new.add_argument("--scripts", action="store_true",
                       help="Include scripts/ with an example script")
    p_new.add_argument("--refs", action="store_true",
                       help="Include references/ and assets/ directories")
    p_new.add_argument("--license", help="License name for frontmatter")
    p_new.add_argument("--author", help="Author for metadata")
    p_new.set_defaults(func=_cmd_new)

    # validate
    p_val = sub.add_parser("validate", help="Validate a skill against the spec")
    p_val.add_argument("path", nargs="?", help="Skill directory (default: nearest)")
    p_val.add_argument("--json", action="store_true")
    p_val.add_argument("--packaging", action="store_true",
                       help="Apply packaging-strict rules (credential files become errors)")
    p_val.set_defaults(func=_cmd_validate)

    # package
    p_pkg = sub.add_parser("package", help="Build a distributable zip")
    p_pkg.add_argument("path", nargs="?", help="Skill directory (default: nearest)")
    p_pkg.add_argument("-o", "--output", help="Output zip path")
    p_pkg.set_defaults(func=_cmd_package)

    # install
    p_inst = sub.add_parser("install", help="Install a skill (dir or zip)")
    p_inst.add_argument("source", help="Skill directory or zip")
    p_inst.add_argument("--user", action="store_true",
                        help="Install to ~/.claude/skills (default: project)")
    p_inst.add_argument("--dest", help="Explicit skills root (e.g. .agents/skills)")
    p_inst.add_argument("--force", action="store_true", help="Replace existing")
    p_inst.set_defaults(func=_cmd_install)

    # list
    p_list = sub.add_parser("list", help="List installed skills")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=_cmd_list)

    # bundle
    p_bundle = sub.add_parser(
        "bundle",
        help="Write or refresh a skill's bundled runtime (scripts/steer.py)")
    p_bundle.add_argument("path", nargs="?",
                          help="Skill directory (default: nearest)")
    p_bundle.add_argument("--with", dest="with_components", default="",
                          help="Components to bundle (default: what the "
                               "existing bundle declares)")
    p_bundle.set_defaults(func=_cmd_bundle)

    register_runtime_commands(sub)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        # Steer raises ValueError for user-fixable input problems
        # (bad skill/flow/process names, bad scopes): print, don't trace.
        return _err(str(exc))
    except KeyboardInterrupt:
        return 130


def run() -> None:
    """Console-script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    run()
