"""The `learn` runtime command (see runtime_cli.py for the plumbing)."""

import json
import sys
from pathlib import Path

from .output import CLI_HINT, output_json
from .paths import find_skill_root
from .runtime_cli import (VENDORED_SKILL_ROOT, _emit, _err, _resolve_skill,
                          runtime_command)
from .skill import Skill, SkillNotFound, discover


def _skill_dir_and_version(skill_name: str):
    """Locate the skill's directory and current version, if findable."""
    candidates = []
    if VENDORED_SKILL_ROOT is not None:
        candidates.append(VENDORED_SKILL_ROOT)
    root = find_skill_root(".")
    if root is not None:
        candidates.append(root)
    for candidate in candidates:
        try:
            skill = Skill.load(candidate)
            if (skill.name or candidate.name) == skill_name:
                return candidate, skill.version
        except SkillNotFound:
            pass
    for skill in discover():
        if (skill.name or skill.dir_name) == skill_name:
            return skill.path, skill.version
    return None, None


def _cmd_learn(args) -> int:
    from .learn import Learnings, LessonRejected, reflect, scan_transcript

    skill = _resolve_skill(args, "this lesson")
    if skill is None:
        return 1

    if args.learn_cmd == "reflect":
        # Stop-hook mode: hook JSON on stdin; print a decision (or nothing).
        # Always exit 0: a broken hook must never break the agent.
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
                print(f"\nPromote the keepers into the skill: "
                      f"{CLI_HINT} learn promote <id>")
                return 0

            if args.learn_cmd == "promote":
                target = Path(args.dir).expanduser() if args.dir else skill_dir
                if target is None:
                    return _err(
                        f"Can't find the skill directory for '{skill}'. "
                        f"Pass it explicitly: {CLI_HINT} learn promote "
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


@runtime_command("learn")
def register_learn_cli(sub) -> None:
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
