"""The `context` runtime command (see runtime_cli.py for the plumbing)."""

from .output import output_json
from .runtime_cli import _err, runtime_command


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


@runtime_command("context")
def register_context_cli(sub) -> None:
    p_ctx = sub.add_parser("context", help="Situational snapshot")
    p_ctx.add_argument("--json", action="store_true")
    p_ctx.add_argument("--only", help="Sections: system,agent,git,project,tools,env")
    p_ctx.add_argument("--tools", help="Extra binaries to probe (comma-separated)")
    p_ctx.add_argument("--workspace", default=".")
    p_ctx.set_defaults(func=_cmd_context)
