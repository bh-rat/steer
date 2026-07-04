"""The `store` runtime command (see runtime_cli.py for the plumbing)."""

import json
import sys

from .output import output_json
from .runtime_cli import _err, _resolve_skill, runtime_command


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


@runtime_command("store")
def register_store_cli(sub) -> None:
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
