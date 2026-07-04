"""The `secrets` runtime command (see runtime_cli.py for the plumbing)."""

import sys

from .output import CLI_HINT, output_json
from .runtime_cli import _emit, _err, _resolve_skill, runtime_command


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
            import getpass

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
            print(f"Store one: {CLI_HINT} secrets set <KEY> --skill {skill}")
            return 0
        for key, origin in known.items():
            state = origin if origin else "MISSING"
            print(f"{key}  ({state})")
        return 0
    return _err(f"Unknown secrets command: {args.secrets_cmd}")


@runtime_command("secrets")
def register_secrets_cli(sub) -> None:
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
