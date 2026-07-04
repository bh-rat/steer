"""
The steer CLI.

Author-time:  steer new | validate | package | install | list
Runtime:      steer secrets | store | context | flow | proc

Every runtime command resolves its skill from --skill, the STEER_SKILL
env var, or the nearest SKILL.md above the working directory. Errors are
written for agents: they say what to run next.
"""

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .output import output_json


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


def _resolve_skill(args, needed_for: str) -> Optional[str]:
    from .paths import infer_skill_name

    name = infer_skill_name(getattr(args, "skill", None))
    if not name:
        _err(
            f"Could not determine which skill {needed_for} belongs to. "
            f"Pass --skill <name>, set STEER_SKILL, or run from inside a "
            f"skill directory."
        )
        return None
    return name


# -- new --------------------------------------------------------------


def _cmd_new(args) -> int:
    from .create import create_skill
    from .validate import summarize, validate_skill

    def _csv(raw):
        return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]

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


# -- validate / package / install / list --------------------------------


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

    path = _resolve_skill_path(args.path)
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


# -- secrets ------------------------------------------------------------


def _cmd_secrets(args) -> int:
    from .secrets import Secrets, remediation_message

    skill = _resolve_skill(args, "this secret")
    if skill is None:
        return 1
    secrets = Secrets(skill)

    if args.secrets_cmd == "set":
        if args.value is not None:
            value = args.value
        elif args.stdin or not sys.stdin.isatty():
            value = sys.stdin.readline().rstrip("\n")
        else:
            value = getpass.getpass(f"Value for {args.key} (input hidden): ")
        if not value:
            return _err("Empty value; nothing stored.")
        backend = secrets.set(args.key, value, backend=args.backend)
        return _emit(args, f"✓ Stored {args.key} for skill '{skill}' ({backend})",
                     key=args.key, skill=skill, backend=backend)

    if args.secrets_cmd == "get":
        value = secrets.get(args.key)
        if value is None:
            if args.json:
                output_json({"ok": False, "key": args.key, "available": False})
            print(remediation_message(skill, args.key), file=sys.stderr)
            return 1
        if args.json:
            output_json({"ok": True, "key": args.key, "value": value})
        else:
            print(value)
        return 0

    if args.secrets_cmd == "check":
        origin = secrets.status(args.key)
        if args.json:
            output_json({"key": args.key, "skill": skill,
                         "available": origin is not None, "origin": origin})
            return 0 if origin else 1
        if origin:
            print(f"✓ {args.key} available ({origin})")
            return 0
        print(remediation_message(skill, args.key), file=sys.stderr)
        return 1

    if args.secrets_cmd == "unset":
        removed = secrets.unset(args.key)
        if removed:
            return _emit(args, f"✓ Removed {args.key} from: {', '.join(removed)}",
                         key=args.key, removed_from=removed)
        return _emit(args, f"{args.key} was not stored by steer (env vars "
                     f"can't be removed by steer).",
                     key=args.key, removed_from=[])

    if args.secrets_cmd == "list":
        known = secrets.list_keys()
        if args.json:
            output_json({"skill": skill, "keys": known})
            return 0
        if not known:
            print(f"No secrets stored for skill '{skill}'.")
            print(f"Store one: steer secrets set <KEY> --skill {skill}")
            return 0
        for key, origin in known.items():
            state = origin if origin else "MISSING"
            print(f"{key}  ({state})")
        return 0
    return _err(f"Unknown secrets command: {args.secrets_cmd}")


# -- store --------------------------------------------------------------


def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _cmd_store(args) -> int:
    from .store import Store

    skill = _resolve_skill(args, "this data")
    if skill is None:
        return 1
    store = Store(skill, scope=args.scope, workspace=args.workspace)

    try:
        if args.store_cmd == "put":
            store.put(args.key, _parse_value(args.value))
            print(f"✓ {args.key} stored ({args.scope} scope)")
            return 0
        if args.store_cmd == "get":
            value = store.get(args.key)
            if value is None:
                print(f"(no value for {args.key!r})", file=sys.stderr)
                return 1
            output_json(value)
            return 0
        if args.store_cmd == "del":
            removed = store.delete(args.key)
            print("✓ deleted" if removed else f"(no value for {args.key!r})")
            return 0
        if args.store_cmd == "keys":
            output_json(store.keys())
            return 0
        if args.store_cmd == "insert":
            doc = json.loads(args.doc)
            if not isinstance(doc, dict):
                return _err("insert expects a JSON object")
            row_id = store.insert(args.table, doc)
            print(f"✓ inserted into {args.table} (id {row_id})")
            return 0
        if args.store_cmd == "find":
            where = {}
            for clause in args.where or []:
                if "=" not in clause:
                    return _err(f"--where expects field=value, got {clause!r}")
                field_name, _, raw = clause.partition("=")
                where[field_name] = _parse_value(raw)
            output_json(store.find(args.table, where or None, limit=args.limit))
            return 0
        if args.store_cmd == "query":
            output_json(store.query(args.sql))
            return 0
        if args.store_cmd == "tables":
            output_json(store.tables())
            return 0
    except (ValueError, json.JSONDecodeError) as exc:
        return _err(str(exc))
    except Exception as exc:  # sqlite errors carry the useful message
        return _err(f"store: {exc}")
    finally:
        store.close()
    return _err(f"Unknown store command: {args.store_cmd}")


# -- learn --------------------------------------------------------------


def _skill_dir_and_version(skill_name: str):
    """Locate the skill's directory and current version, if findable."""
    from .paths import find_skill_root
    from .skill import Skill, SkillNotFound, discover

    root = find_skill_root(".")
    if root is not None:
        try:
            skill = Skill.load(root)
            if (skill.name or root.name) == skill_name:
                return root, skill.version
        except SkillNotFound:
            pass
    for skill in discover():
        if (skill.name or skill.dir_name) == skill_name:
            return skill.path, skill.version
    return None, None


def _cmd_learn(args) -> int:
    from .learn import Learnings, LessonRejected

    skill = _resolve_skill(args, "this lesson")
    if skill is None:
        return 1

    if args.learn_cmd == "reflect":
        # Stop-hook mode: hook JSON on stdin; print a decision (or nothing).
        # Always exit 0: a broken hook must never break the agent.
        from .learn import reflect, scan_transcript

        try:
            if args.transcript:
                hook_input = {"transcript_path": args.transcript,
                              "stop_hook_active": False}
            else:
                hook_input = json.loads(sys.stdin.read() or "{}")
            if args.scan_only:
                output_json(scan_transcript(
                    hook_input.get("transcript_path", "")))
                return 0
            decision = reflect(hook_input, skill,
                               min_signals=args.min_signals)
            if decision is not None:
                output_json(decision)
        except Exception as exc:  # never block the host agent on a bug
            print(f"steer learn reflect: {exc}", file=sys.stderr)
        return 0

    skill_dir, version = _skill_dir_and_version(skill)

    with Learnings(skill) as learnings:
        try:
            if args.learn_cmd == "note":
                result = learnings.note(
                    args.text, kind=args.kind, context=args.context,
                    evidence=args.evidence, skill_version=version,
                    workspace=str(Path.cwd()),
                )
                verb = ("✓ Lesson recorded" if result["action"] == "added"
                        else "✓ Already known; confirmation strengthened")
                return _emit(args, f"{verb} (id {result['id']})",
                             id=result["id"], action=result["action"])

            if args.learn_cmd == "show":
                digest = learnings.digest(budget=args.budget,
                                          current_version=version)
                if args.json:
                    output_json({"skill": skill, "digest": digest})
                else:
                    print(digest)
                return 0

            if args.learn_cmd in ("confirm", "dispute"):
                action = (learnings.confirm if args.learn_cmd == "confirm"
                          else learnings.dispute)
                lesson = action(args.id)
                score = lesson["confirmations"] - lesson["contradictions"]
                state = (f"score {score:+d}"
                         if lesson["status"] != "archived"
                         else "auto-archived (disputed more than confirmed)")
                return _emit(args, f"✓ Lesson {args.id}: {state}",
                             id=args.id, status=lesson["status"], score=score)

            if args.learn_cmd == "pin":
                learnings.pin(args.id)
                return _emit(args, f"✓ Lesson {args.id} pinned (always shown first).",
                             id=args.id)

            if args.learn_cmd == "forget":
                learnings.forget(args.id)
                return _emit(args, f"✓ Lesson {args.id} archived.", id=args.id)

            if args.learn_cmd == "review":
                statuses = (["pinned", "active", "archived", "promoted"]
                            if args.all else None)
                rows = learnings.lessons(statuses)
                if args.json:
                    output_json(rows)
                    return 0
                if not rows:
                    print(f"No lessons for skill '{skill}' yet.")
                    return 0
                for lesson in rows:
                    score = lesson["confirmations"] - lesson["contradictions"]
                    flags = lesson["status"] if lesson["status"] != "active" else ""
                    print(f"[{lesson['id']:>4}] {score:+d} {lesson['kind']:<10}"
                          f" {flags:<9} {lesson['text']}")
                    if lesson["context"]:
                        print(f"{'':>6} when: {lesson['context']}")
                print("\nPromote the keepers into the skill: "
                      "steer learn promote <id>")
                return 0

            if args.learn_cmd == "promote":
                target = Path(args.dir).expanduser() if args.dir else skill_dir
                if target is None:
                    return _err(
                        f"Can't find the skill directory for '{skill}'. "
                        f"Pass it explicitly: steer learn promote "
                        f"{args.id} --dir <skill-dir>"
                    )
                path = learnings.promote(args.id, target)
                if args.json:
                    output_json({"ok": True, "id": args.id, "path": str(path)})
                    return 0
                print(f"✓ Promoted lesson {args.id} into {path}")
                print("  Make sure SKILL.md tells the agent to read "
                      "`learnings.md` before relying on the main instructions, "
                      "then commit/re-package the skill.")
                return 0

            if args.learn_cmd == "run":
                learnings.record_run(args.status, note=args.note,
                                     skill_version=version,
                                     workspace=str(Path.cwd()))
                return _emit(args, f"✓ Run recorded ({args.status}).",
                             status=args.status)

            if args.learn_cmd == "stats":
                stats = learnings.stats()
                if args.json:
                    output_json(stats)
                    return 0
                runs = stats["runs"]
                rate = (f"{stats['success_rate'] * 100:.0f}%"
                        if stats["success_rate"] is not None else "n/a")
                print(f"{skill}: {runs['total']} runs recorded "
                      f"({runs['ok']} ok, {runs['failed']} failed, "
                      f"success {rate})")
                lessons = stats["lessons"]
                parts = [f"{n} {status}" for status, n in sorted(lessons.items())]
                print(f"lessons: {', '.join(parts) if parts else 'none'}")
                if stats["last_run"]:
                    print(f"last run: {stats['last_run']}")
                return 0

        except LessonRejected as exc:
            return _err(str(exc))
        except Exception as exc:  # corrupt lessons.db etc.; match store's UX
            return _err(f"learn: {exc}")
    return _err(f"Unknown learn command: {args.learn_cmd}")


# -- context ------------------------------------------------------------


def _cmd_context(args) -> int:
    from .context import gather, to_markdown

    only = None
    if args.only:
        only = [s.strip() for s in args.only.split(",") if s.strip()]
    tools = None
    if args.tools:
        tools = [t.strip() for t in args.tools.split(",") if t.strip()]
    try:
        snapshot = gather(workspace=args.workspace, only=only, tools=tools)
    except ValueError as exc:
        return _err(str(exc))
    if args.json:
        output_json(snapshot)
    else:
        print(to_markdown(snapshot))
    return 0


# -- flow ---------------------------------------------------------------


def _load_cli_flow(args):
    """Resolve the flow definition for flow subcommands."""
    from .flow import find_flow_file, load_flow
    from .paths import find_skill_root
    from .skill import discover

    if args.file:
        return load_flow(args.file, workspace=args.workspace)

    if args.skill:
        for skill in discover():
            if (skill.name or skill.dir_name) == args.skill:
                flow_file = find_flow_file(skill.path)
                if flow_file is None:
                    raise FileNotFoundError(
                        f"Skill '{args.skill}' has no flow.toml"
                    )
                return load_flow(flow_file, workspace=args.workspace)
        raise FileNotFoundError(
            f"No installed skill named '{args.skill}' "
            f"(steer list shows what's installed)"
        )

    root = find_skill_root(".")
    if root:
        flow_file = find_flow_file(root)
        if flow_file:
            return load_flow(flow_file, workspace=args.workspace)
    direct = Path("flow.toml")
    if direct.is_file():
        from .flow import load_flow as _load
        return _load(direct, workspace=args.workspace)
    raise FileNotFoundError(
        "No flow found. Pass --file <flow.toml>, --skill <name>, or run "
        "from a directory containing flow.toml."
    )


def _cmd_flow(args) -> int:
    from .renderer import render_workflow

    try:
        flow = _load_cli_flow(args)
    except (FileNotFoundError, ValueError) as exc:
        return _err(str(exc))

    ctx = flow.context(args.workspace)

    if args.flow_cmd == "status":
        render_workflow(flow, ctx, format="json" if args.json else "text")
        return 0

    if args.flow_cmd == "next":
        directive = flow.get_directive(ctx)
        if args.json:
            output_json(directive.to_dict() if directive else {"status": "complete"})
        else:
            from .renderer import render_directive
            if directive is None or directive.status.value == "complete":
                print("✓ All steps complete.")
            else:
                render_directive(directive)
        return 0

    if args.flow_cmd == "done":
        from .flow import FlowBlockedError

        try:
            marked = flow.mark_complete(args.step_id, args.workspace)
        except FlowBlockedError as exc:
            print(f"Not so fast: {exc}", file=sys.stderr)
            print("Run `steer flow next` to see the current step.",
                  file=sys.stderr)
            return 1
        except ValueError as exc:
            return _err(str(exc))
        if not marked:
            print(f"'{args.step_id}' is a verified step; it completes when "
                  f"reality matches its verify condition, not by marking.")
            return 1
        print(f"✓ Marked '{args.step_id}' complete.")
        flow.nudge(args.step_id, flow.context(args.workspace))
        return 0

    if args.flow_cmd == "reset":
        flow.reset(args.step_id, args.workspace)
        target = args.step_id or "all mandate steps"
        print(f"✓ Reset {target}.")
        return 0
    return _err(f"Unknown flow command: {args.flow_cmd}")


# -- proc ---------------------------------------------------------------


def _cmd_proc(args) -> int:
    from .proc import ProcError, list_procs, logs, start, status, stop

    try:
        if args.proc_cmd == "start":
            command = list(args.command or [])
            if command and command[0] == "--":
                command = command[1:]
            info = start(
                args.name, command, workspace=args.workspace,
                ready_port=args.ready_port, ready_log=args.ready_log,
                timeout=args.timeout, cwd=args.cwd,
            )
            if args.json:
                output_json(info)
            else:
                port = f" (port {info['ready_port']} open)" if info.get("port_open") else ""
                print(f"✓ Started '{args.name}' (pid {info['pid']}){port}")
                print(f"  log: {info['log']}")
                print(f"  stop with: steer proc stop {args.name}")
            return 0
        if args.proc_cmd == "stop":
            info = stop(args.name, workspace=args.workspace)
            if args.json:
                output_json(info)
            elif info.get("stopped"):
                forced = " (forced)" if info.get("forced") else ""
                print(f"✓ Stopped '{args.name}'{forced}")
            else:
                print(f"'{args.name}' was not running.")
            return 0
        if args.proc_cmd == "status":
            if args.name:
                info = status(args.name, workspace=args.workspace)
                if args.json:
                    output_json(info)
                elif not info.get("known"):
                    print(f"No managed process named '{args.name}'.")
                    return 1
                else:
                    state = "running" if info["running"] else "stopped"
                    print(f"{args.name}: {state} (pid {info.get('pid')}, "
                          f"started {info.get('started_at')})")
                return 0
            infos = list_procs(args.workspace)
            if args.json:
                output_json(infos)
            elif not infos:
                print("No managed processes in this workspace.")
            else:
                for info in infos:
                    state = "running" if info["running"] else "stopped"
                    print(f"{info['name']}: {state} (pid {info.get('pid')})")
            return 0
        if args.proc_cmd == "logs":
            print(logs(args.name, workspace=args.workspace, lines=args.lines))
            return 0
    except ProcError as exc:
        return _err(str(exc))
    return _err(f"Unknown proc command: {args.proc_cmd}")


# -- parser ---------------------------------------------------------------


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
                            "lesson capture (implies learn; Claude-Code-only)")
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

    # secrets
    p_sec = sub.add_parser("secrets", help="Per-skill credentials")
    sec_sub = p_sec.add_subparsers(dest="secrets_cmd", required=True)
    for cmd, needs_key in (("set", True), ("get", True), ("check", True),
                           ("unset", True), ("list", False)):
        sp = sec_sub.add_parser(cmd)
        if needs_key:
            sp.add_argument("key", help="Secret name, e.g. STRIPE_API_KEY")
        if cmd == "set":
            sp.add_argument("value", nargs="?",
                            help="Value (prefer --stdin or the hidden prompt; "
                                 "argv leaks into shell history)")
            sp.add_argument("--stdin", action="store_true",
                            help="Read the value from stdin")
            sp.add_argument("--backend", default="auto",
                            choices=("auto", "keychain", "file"))
        sp.add_argument("--skill", help="Skill name (default: inferred)")
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=_cmd_secrets)

    # store
    p_store = sub.add_parser("store", help="Per-skill SQLite storage")
    store_sub = p_store.add_subparsers(dest="store_cmd", required=True)
    specs = {
        "put": [("key",), ("value",)],
        "get": [("key",)],
        "del": [("key",)],
        "keys": [],
        "insert": [("table",), ("doc",)],
        "find": [("table",)],
        "query": [("sql",)],
        "tables": [],
    }
    for cmd, positionals in specs.items():
        sp = store_sub.add_parser(cmd)
        for (arg_name,) in positionals:
            sp.add_argument(arg_name)
        if cmd == "find":
            sp.add_argument("--where", action="append",
                            help="field=value filter (repeatable)")
            sp.add_argument("--limit", type=int)
        sp.add_argument("--skill", help="Skill name (default: inferred)")
        sp.add_argument("--scope", default="user", choices=("user", "workspace"))
        sp.add_argument("--workspace", default=".")
        sp.set_defaults(func=_cmd_store)

    # learn
    p_learn = sub.add_parser("learn",
                             help="Lessons a skill accumulates from its runs")
    learn_sub = p_learn.add_subparsers(dest="learn_cmd", required=True)
    lp = learn_sub.add_parser("note", help="Record a lesson")
    lp.add_argument("text", help="The lesson: one imperative rule, no secrets")
    lp.add_argument("--kind", default="note",
                    choices=("correction", "failure", "success",
                             "preference", "note"))
    lp.add_argument("--context", help="When this applies (trigger condition)")
    lp.add_argument("--evidence", help="Provenance: file, command, or error")
    lp = learn_sub.add_parser("show",
                              help="Bounded digest to read at run start")
    lp.add_argument("--budget", type=int, default=2000,
                    help="Max characters (default 2000)")
    for cmd, help_text in (("confirm", "This lesson helped"),
                           ("dispute", "This lesson was wrong"),
                           ("pin", "Always show first"),
                           ("forget", "Archive a lesson")):
        lp = learn_sub.add_parser(cmd, help=help_text)
        lp.add_argument("id", type=int)
    lp = learn_sub.add_parser("review", help="List lessons with scores")
    lp.add_argument("--all", action="store_true",
                    help="Include archived and promoted lessons")
    lp = learn_sub.add_parser("promote",
                              help="Graduate a lesson into the skill's "
                                   "learnings.md")
    lp.add_argument("id", type=int)
    lp.add_argument("--dir", help="Skill directory (default: resolved)")
    lp = learn_sub.add_parser("run", help="Record a run outcome")
    lp.add_argument("status", choices=("ok", "failed"))
    lp.add_argument("--note", help="What happened")
    learn_sub.add_parser("stats", help="Run counts and lesson totals")
    lp = learn_sub.add_parser(
        "reflect",
        help="Stop-hook auto-learning: scan the session transcript for "
             "corrections/failures and prompt the agent to distill lessons")
    lp.add_argument("--transcript", help="Transcript path (default: from "
                                         "hook JSON on stdin)")
    lp.add_argument("--min-signals", type=int, default=1,
                    help="Signals required before prompting (default 1)")
    lp.add_argument("--scan-only", action="store_true",
                    help="Print the signal scan and exit")
    for lpx in learn_sub.choices.values():
        lpx.add_argument("--skill", help="Skill name (default: inferred)")
        lpx.add_argument("--json", action="store_true")
        lpx.set_defaults(func=_cmd_learn)

    # context
    p_ctx = sub.add_parser("context", help="Situational snapshot")
    p_ctx.add_argument("--json", action="store_true")
    p_ctx.add_argument("--only", help="Sections: system,agent,git,project,tools,env")
    p_ctx.add_argument("--tools", help="Extra binaries to probe (comma-separated)")
    p_ctx.add_argument("--workspace", default=".")
    p_ctx.set_defaults(func=_cmd_context)

    # flow
    p_flow = sub.add_parser("flow", help="Run a skill's multi-step flow")
    flow_sub = p_flow.add_subparsers(dest="flow_cmd", required=True)
    for cmd in ("status", "next", "done", "reset"):
        sp = flow_sub.add_parser(cmd)
        if cmd == "done":
            sp.add_argument("step_id", help="Mandate step to mark complete")
        if cmd == "reset":
            sp.add_argument("step_id", nargs="?",
                            help="Step to reset (default: all mandate steps)")
        sp.add_argument("--file", help="Path to a flow.toml")
        sp.add_argument("--skill", help="Installed skill whose flow to run")
        sp.add_argument("--workspace", default=".",
                        help="Workspace the flow operates on (default: .)")
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=_cmd_flow)

    # proc
    p_proc = sub.add_parser("proc", help="Managed background processes")
    proc_sub = p_proc.add_subparsers(dest="proc_cmd", required=True)
    sp = proc_sub.add_parser("start")
    sp.add_argument("name")
    sp.add_argument("--ready-port", type=int, help="Wait until this port accepts")
    sp.add_argument("--ready-log", help="Wait until this text appears in the log")
    sp.add_argument("--timeout", type=float, default=30.0)
    sp.add_argument("--cwd", help="Working directory for the process")
    sp.add_argument("command", nargs="*",
                    help="The command to run, after a -- separator: "
                         "steer proc start web --ready-port 5173 -- npm run dev")
    for cmd in ("stop", "logs"):
        spc = proc_sub.add_parser(cmd)
        spc.add_argument("name")
        if cmd == "logs":
            spc.add_argument("-n", "--lines", type=int, default=50)
    sps = proc_sub.add_parser("status")
    sps.add_argument("name", nargs="?")
    for spx in (sp, sps, *[proc_sub.choices[c] for c in ("stop", "logs")]):
        spx.add_argument("--workspace", default=".")
        spx.add_argument("--json", action="store_true")
    for spx in proc_sub.choices.values():
        spx.set_defaults(func=_cmd_proc)

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
