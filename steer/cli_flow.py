"""The `flow` runtime command (see runtime_cli.py for the plumbing)."""

import sys
from pathlib import Path

from .output import CLI_HINT, output_json
from .paths import find_skill_root
from .runtime_cli import VENDORED_SKILL_ROOT, _err, runtime_command
from .skill import discover


def _load_cli_flow(args):
    """Resolve the flow definition for flow subcommands."""
    from .flow import find_flow_file, load_flow

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

    roots = [VENDORED_SKILL_ROOT, find_skill_root(".")]
    for root in roots:
        if root is None:
            continue
        flow_file = find_flow_file(root)
        if flow_file:
            return load_flow(flow_file, workspace=args.workspace)
    direct = Path("flow.toml")
    if direct.is_file():
        return load_flow(direct, workspace=args.workspace)
    raise FileNotFoundError(
        "No flow found. Pass --file <flow.toml>, --skill <name>, or run "
        "from a directory containing flow.toml."
    )


def _cmd_flow(args) -> int:
    from .flow import FlowBlockedError
    from .renderer import render_directive, render_workflow

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
            if directive is None or directive.status.value == "complete":
                print("✓ All steps complete.")
            else:
                render_directive(directive)
        return 0

    if args.flow_cmd == "done":
        try:
            marked = flow.mark_complete(args.step_id, args.workspace)
        except FlowBlockedError as exc:
            print(f"Not so fast: {exc}", file=sys.stderr)
            print(f"Run `{CLI_HINT} flow next` to see the current step.",
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


@runtime_command("flow")
def register_flow_cli(sub) -> None:
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
