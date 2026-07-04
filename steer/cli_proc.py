"""The `proc` runtime command (see runtime_cli.py for the plumbing)."""

from .output import CLI_HINT, output_json
from .runtime_cli import _err, runtime_command


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
                print(f"  stop with: {CLI_HINT} proc stop {args.name}")
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


@runtime_command("proc")
def register_proc_cli(sub) -> None:
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
