"""
The bundled runtime: a self-contained scripts/steer.py inside a skill.

Skills built with steer call runtime components (secrets, store, flow,
proc, learn, context) while they run. Requiring every consumer of a
skill to install steer for that would tax distribution, so `steer new`
copies the runtime INTO the skill instead: this module amalgamates the
component modules the skill actually uses, plus the shared plumbing,
into one stdlib-only file the skill invokes as
`python3 scripts/steer.py <command>` and sibling scripts import as
`from steer import Store`.

The output is deterministic for a given (steer version, component set):
the same bytes everywhere, so a bundle can be verified by regenerating
it. A `# steer-runtime:` header line carries the version and component
list; validate and package use it to detect stale or edited bundles.

Amalgamation rules the source modules must follow (generate() enforces
the last three; tests enforce the first): top-level names must be unique
across modules (byte-identical duplicates excepted); relative imports
must name symbols (`from .paths import steer_home`), never modules
(`from . import x`), because imports are rewritten for the flat
namespace (plain ones become `pass`, aliased ones become `alias = name`
assignments); a top-level aliased import must come from a module earlier
in bundle order (the assignment runs eagerly); and nothing may read the
seam globals (CLI_HINT, VENDORED_SKILL_ROOT) at module time, since the
bundle's entry point rebinds them only after every module body has run.
"""

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from . import __version__

# Shared plumbing every bundle carries: path conventions, the output
# envelope, and the SKILL.md model (skill/flow resolution reads it).
BASE_MODULES = ("paths", "output", "frontmatter", "skill")

# Component -> source modules it brings along.
COMPONENT_MODULES = {
    "secrets": ("secrets",),
    "store": ("store",),
    "context": ("context",),
    "flow": ("flow", "renderer"),
    "proc": ("proc",),
    "learn": ("learn",),
}

RUNTIME_REL_PATH = Path("scripts") / "steer.py"
RUNTIME_PROG = "python3 scripts/steer.py"

_HEADER_MARK = "# steer-runtime:"

# Rebound by the bundle's entry point after all module bodies have run;
# reading them at module time would freeze the pre-rebind value.
_SEAM_NAMES = frozenset({"CLI_HINT", "VENDORED_SKILL_ROOT"})


class VendorError(ValueError):
    """A module violates the amalgamation rules."""


def normalize_components(components: Iterable[str]) -> List[str]:
    """Validate and put components in canonical order; raises ValueError."""
    chosen = {c.strip() for c in components if c and c.strip()}
    unknown = chosen - set(COMPONENT_MODULES)
    if unknown:
        raise ValueError(
            f"Unknown component(s): {', '.join(sorted(unknown))} "
            f"(available: {', '.join(COMPONENT_MODULES)})"
        )
    if not chosen:
        raise ValueError("No components to bundle")
    return [c for c in COMPONENT_MODULES if c in chosen]


def _rewrite_relative_imports(module: str, source: str, tree: ast.Module,
                              known: set) -> str:
    """Replace relative imports with flat-namespace equivalents.

    `from .x import a` needs nothing (a is a global after amalgamation)
    and becomes `pass`; `from .x import a as b` becomes `b = a`. Module
    imports (`from . import x`) have no flat equivalent and are refused.

    A top-level alias assignment runs eagerly, so its source name must
    already be `known` (defined by a module earlier in bundle order);
    aliases inside functions run at call time and are unconstrained.
    """
    top_level = set(tree.body)
    spans: List[Tuple[int, int, str, str]] = []  # (first, last, indent, text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.level:
            continue
        if node.module is None:
            raise VendorError(
                f"steer/{module}.py:{node.lineno}: `from . import ...` has "
                f"no flat-namespace equivalent; import the symbols instead "
                f"(`from .{node.names[0].name} import <name>`)"
            )
        aliases = [(a.name, a.asname) for a in node.names
                   if a.asname and a.asname != a.name]
        if node in top_level:
            for name, asname in aliases:
                if name not in known:
                    raise VendorError(
                        f"steer/{module}.py:{node.lineno}: `{name} as "
                        f"{asname}` becomes an eager assignment, but "
                        f"{name!r} is not defined by an earlier module in "
                        f"bundle order; reorder, or drop the alias"
                    )
        replacement = ("; ".join(f"{asname} = {name}"
                                 for name, asname in aliases)
                       or "pass")
        spans.append((node.lineno, node.end_lineno, node.col_offset * " ",
                      replacement))

    lines = source.splitlines()
    for first, last, indent, replacement in sorted(spans, reverse=True):
        lines[first - 1:last] = [f"{indent}{replacement}"]
    return "\n".join(lines) + "\n"


def _top_level_names(tree: ast.Module) -> set:
    """Names a module body binds at its top level (defs, classes, assigns,
    imports, and the LHS of rewritten aliased imports)."""
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets
                         if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target,
                                                            ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0]
                         for a in node.names)
    return names


def _check_no_module_time_seam_reads(module: str, tree: ast.Module) -> None:
    """Refuse module-time reads of the seam globals.

    Function bodies read them at call time (after the entry point rebinds
    them); anything else, including default argument values and
    decorators, would freeze the pre-rebind value into the bundle.
    """

    def visit(node) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda)):
            deferred_args = node.args
            for default in (*deferred_args.defaults,
                            *filter(None, deferred_args.kw_defaults)):
                visit(default)
            for decorator in getattr(node, "decorator_list", []):
                visit(decorator)
            return
        if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                and node.id in _SEAM_NAMES):
            raise VendorError(
                f"steer/{module}.py:{node.lineno}: {node.id} is read at "
                f"module time, before the bundle entry point rebinds it; "
                f"move the read inside a function"
            )
        for child in ast.iter_child_nodes(node):
            visit(child)

    for statement in tree.body:
        visit(statement)


def _module_source(module: str) -> str:
    return (Path(__file__).parent / f"{module}.py").read_text(encoding="utf-8")


def _bundle_modules(components: List[str]) -> List[str]:
    modules = list(BASE_MODULES)
    for component in components:
        modules.extend(COMPONENT_MODULES[component])
    modules.append("runtime_cli")
    return modules


def generate(components: Iterable[str]) -> str:
    """Return the bundled-runtime source for these components."""
    return _generate(tuple(normalize_components(components)))


@lru_cache(maxsize=None)  # pure per (steer version, component set); ~64 combos
def _generate(chosen: Tuple[str, ...]) -> str:
    modules = _bundle_modules(list(chosen))
    joined = ",".join(chosen)

    parts = [f'''\
#!/usr/bin/env python3
{_HEADER_MARK} version={__version__} components={joined}
# Generated by steer; DO NOT EDIT. Regenerate: steer bundle --with {joined}
#
# This is the skill's bundled steer runtime, amalgamated from the steer
# package (https://github.com/bh-rat/steer, MIT) so the skill runs
# without steer installed. SKILL.md calls it ({RUNTIME_PROG}
# <command>) and sibling scripts can import it (from steer import ...).
# Python 3.11+, stdlib only. State lives under ~/.steer and
# <workspace>/.steer, same as the installed CLI.
"""Bundled steer runtime for this skill (generated; do not edit)."""

__version__ = "{__version__}"
STEER_RUNTIME_COMPONENTS = ({", ".join(repr(c) for c in chosen)},)
''']
    known: set = set()
    for module in modules:
        source = _module_source(module)
        tree = ast.parse(source)
        _check_no_module_time_seam_reads(module, tree)
        rewritten = _rewrite_relative_imports(module, source, tree, known)
        known |= _top_level_names(tree)
        parts.append(f"\n# ===== steer/{module}.py =====\n\n{rewritten}")

    submodules = ", ".join(repr(m) for m in modules)
    parts.append(f'''
# ===== entry point =====

import shlex as _shlex
import sys as _sys
from pathlib import Path as _Path

# The bundle knows which skill it belongs to: the one it ships inside.
# Hints spell this file by absolute path so they run from any directory
# (the agent's working directory is usually the workspace, not the skill).
VENDORED_SKILL_ROOT = _Path(__file__).resolve().parent.parent
CLI_HINT = "python3 " + _shlex.quote(str(_Path(__file__).resolve()))

# Sibling scripts import this file as `steer`; alias the module paths the
# package would provide so `from steer.output import ...` keeps working.
_self = _sys.modules.get(__name__)
if _self is not None:
    _sys.modules.setdefault("steer", _self)
    for _submodule in ({submodules}):
        _sys.modules.setdefault(f"steer.{{_submodule}}", _self)

if __name__ == "__main__":
    _sys.exit(runtime_main(
        components=list(STEER_RUNTIME_COMPONENTS),
        prog="{RUNTIME_PROG}",
        version=__version__,
    ))
''')
    source = "".join(parts)
    compile(source, str(RUNTIME_REL_PATH), "exec")  # refuse to emit broken code
    return source


@dataclass
class RuntimeHeader:
    """The machine-readable first comment of a bundled runtime."""
    version: str
    components: List[str]
    path: Path


def read_runtime_header(skill_dir) -> Optional[RuntimeHeader]:
    """Parse the bundle's header line; None when no bundle exists."""
    path = Path(skill_dir) / RUNTIME_REL_PATH
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            head = [fh.readline() for _ in range(5)]
    except OSError:
        return None
    for line in head:
        if not line.startswith(_HEADER_MARK):
            continue
        fields = dict(part.split("=", 1) for part in line[len(_HEADER_MARK):].split()
                      if "=" in part)
        if "version" not in fields or "components" not in fields:
            return None
        components = [c for c in fields["components"].split(",") if c]
        return RuntimeHeader(fields["version"], components, path)
    return None


def runtime_state(skill_dir,
                  header: Optional[RuntimeHeader] = None) -> Optional[str]:
    """How a skill's bundle relates to this steer: 'fresh' | 'stale' | 'edited'.

    None when there is no bundle (or no parseable header, which validate
    reports the same way). 'stale' means another steer version wrote it;
    'edited' means this version's output for the declared components
    doesn't match the file. Pass an already-parsed `header` to skip
    re-reading it.
    """
    if header is None:
        header = read_runtime_header(skill_dir)
    if header is None:
        return None
    if header.version != __version__:
        return "stale"
    try:
        expected = generate(header.components)
    except ValueError:
        return "edited"
    current = header.path.read_text(encoding="utf-8", errors="replace")
    return "fresh" if current == expected else "edited"


def write_runtime(skill_dir, components: Iterable[str]) -> Path:
    """Write (or refresh) the bundled runtime; returns its path."""
    source = generate(components)
    target = Path(skill_dir) / RUNTIME_REL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    target.chmod(target.stat().st_mode | 0o755)
    return target
