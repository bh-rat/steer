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
The file is shaped like a hand-written module, docstring, then one
deduplicated import block, then constants and the module sections, so
it passes the same linting as any other checked-in Python.

Amalgamation rules the source modules must follow (generate() enforces
all but the first; tests enforce that one): top-level names must be
unique across modules (byte-identical duplicates excepted); top-level
absolute imports are hoisted into the bundle's import block, so two
modules must not bind the same name from different sources; relative
imports must name symbols (`from .paths import steer_home`), never
modules (`from . import x`), because they are rewritten for the flat
namespace (dropped at top level, `pass` inside functions, aliased ones
become `alias = name` assignments); a top-level aliased import must come
from a module earlier in bundle order (the assignment runs eagerly); and
nothing may read the seam globals (CLI_HINT, VENDORED_SKILL_ROOT) at
module time, since the bundle's entry point rebinds them only after
every module body has run.
"""

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from . import __version__
from .runtime_cli import COMPONENT_ORDER

# Shared plumbing every bundle carries: path conventions, the output
# envelope, the SKILL.md model (skill/flow resolution reads it), and the
# runtime CLI core the cli_<component> modules register into.
BASE_MODULES = ("paths", "output", "frontmatter", "skill", "runtime_cli")

# Component -> source modules it brings along (its library plus its CLI;
# a bundle contains no code for components it lacks). Keys follow
# COMPONENT_ORDER; a test pins that.
COMPONENT_MODULES = {
    "secrets": ("secrets", "cli_secrets"),
    "store": ("store", "cli_store"),
    "context": ("context", "cli_context"),
    "flow": ("flow", "renderer", "cli_flow"),
    "proc": ("proc", "cli_proc"),
    "learn": ("learn", "cli_learn"),
}
assert tuple(COMPONENT_MODULES) == COMPONENT_ORDER

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


class _HoistedImports:
    """The bundle's single import block.

    Every module's top-level absolute imports land here, deduplicated,
    in place of the scattered mid-file copies concatenation would
    produce (which both re-run per section and fail linting: E402,
    F811). Two modules binding the same name from different sources is
    an amalgamation conflict and is refused.
    """

    def __init__(self):
        self._plain: Dict[Tuple[str, Optional[str]], None] = {}
        self._named: Dict[str, Dict[str, Optional[str]]] = {}
        self._bound: Dict[str, str] = {}  # binding name -> source statement

    def _bind(self, module: str, lineno: int, binding: str,
              statement: str) -> None:
        previous = self._bound.get(binding)
        if previous is not None and previous != statement:
            raise VendorError(
                f"steer/{module}.py:{lineno}: `{statement}` binds "
                f"{binding!r}, which the bundle already binds via "
                f"`{previous}`; the hoisted import block can keep only one"
            )
        self._bound[binding] = statement

    def collect(self, module: str, tree: ast.Module) -> None:
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    binding = alias.asname or alias.name.split(".")[0]
                    statement = f"import {alias.name}" + (
                        f" as {alias.asname}" if alias.asname else "")
                    self._bind(module, node.lineno, binding, statement)
                    self._plain[(alias.name, alias.asname)] = None
            elif isinstance(node, ast.ImportFrom) and not node.level:
                if node.module == "__future__":
                    raise VendorError(
                        f"steer/{module}.py:{node.lineno}: __future__ "
                        f"imports cannot be amalgamated (and steer targets "
                        f"Python 3.11+; none should be needed)")
                for alias in node.names:
                    binding = alias.asname or alias.name
                    statement = f"from {node.module} import {alias.name}" + (
                        f" as {alias.asname}" if alias.asname else "")
                    self._bind(module, node.lineno, binding, statement)
                    self._named.setdefault(node.module, {})[alias.name] = (
                        alias.asname)

    def require(self, module: str) -> None:
        """An import the generated entry point needs regardless of modules."""
        self._bind("<entry point>", 0, module, f"import {module}")
        self._plain[(module, None)] = None

    def require_from(self, module: str, name: str) -> None:
        self._bind("<entry point>", 0, name, f"from {module} import {name}")
        self._named.setdefault(module, {})[name] = None

    def bindings(self) -> set:
        return set(self._bound)

    def render(self) -> str:
        lines = [f"import {name}" + (f" as {asname}" if asname else "")
                 for name, asname in sorted(self._plain,
                                            key=lambda k: (k[0], k[1] or ""))]
        for module in sorted(self._named):
            entries = ", ".join(
                name + (f" as {asname}" if asname else "")
                for name, asname in sorted(self._named[module].items()))
            lines.append(f"from {module} import {entries}")
        return "\n".join(lines)


def _rewrite_module_imports(module: str, source: str, tree: ast.Module,
                            known: set) -> str:
    """Rewrite a module body for the flat namespace.

    Top-level absolute imports disappear (they live in the hoisted
    block). Relative imports have no module to import from: at top level
    they are dropped, inside functions they become `pass` (the names
    resolve as globals at call time), and `from .x import a as b`
    becomes a `b = a` assignment. Module imports (`from . import x`)
    have no flat equivalent and are refused.

    A top-level alias assignment runs eagerly, so its source name must
    already be `known` (hoisted, or defined by an earlier module);
    aliases inside functions run at call time and are unconstrained.
    """
    top_level = set(tree.body)
    # (first_line, last_line, replacement_lines)
    spans: List[Tuple[int, int, List[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) or (
                isinstance(node, ast.ImportFrom) and not node.level):
            if node in top_level:
                spans.append((node.lineno, node.end_lineno, []))
            continue
        if not isinstance(node, ast.ImportFrom):
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
        indent = node.col_offset * " "
        if aliases:
            replacement = [indent + "; ".join(f"{asname} = {name}"
                                              for name, asname in aliases)]
        else:
            replacement = [] if node in top_level else [f"{indent}pass"]
        spans.append((node.lineno, node.end_lineno, replacement))

    lines = source.splitlines()
    for first, last, replacement in sorted(spans, reverse=True):
        lines[first - 1:last] = replacement
    return "\n".join(lines) + "\n"


def _top_level_names(tree: ast.Module) -> set:
    """Names a module body binds at its top level (defs, classes, assigns,
    and the LHS of rewritten aliased imports)."""
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
        elif isinstance(node, ast.ImportFrom) and node.level:
            names.update(a.asname for a in node.names
                         if a.asname and a.asname != a.name)
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
    # runtime_cli (in BASE_MODULES) precedes the cli_<component> modules:
    # their @runtime_command registrations run at module-body time.
    modules = list(BASE_MODULES)
    for component in components:
        modules.extend(COMPONENT_MODULES[component])
    return modules


def generate(components: Iterable[str]) -> str:
    """Return the bundled-runtime source for these components."""
    return _generate(tuple(normalize_components(components)))


@lru_cache(maxsize=None)  # pure per (steer version, component set); ~64 combos
def _generate(chosen: Tuple[str, ...]) -> str:
    modules = _bundle_modules(list(chosen))
    joined = ",".join(chosen)

    sources: Dict[str, str] = {}
    trees: Dict[str, ast.Module] = {}
    imports = _HoistedImports()
    for module in modules:
        sources[module] = _module_source(module)
        trees[module] = ast.parse(sources[module])
        _check_no_module_time_seam_reads(module, trees[module])
        imports.collect(module, trees[module])
    # The entry point below needs these whatever the component set.
    imports.require("shlex")
    imports.require("sys")
    imports.require_from("pathlib", "Path")

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

{imports.render()}

__version__ = "{__version__}"
STEER_RUNTIME_COMPONENTS = ({", ".join(repr(c) for c in chosen)},)
''']
    known: set = imports.bindings()
    for module in modules:
        rewritten = _rewrite_module_imports(module, sources[module],
                                            trees[module], known)
        known |= _top_level_names(trees[module])
        parts.append(f"\n# ===== steer/{module}.py =====\n\n{rewritten}")

    submodules = ", ".join(repr(m) for m in modules)
    parts.append(f'''
# ===== entry point =====

# The bundle knows which skill it belongs to: the one it ships inside.
# Hints spell this file by absolute path so they run from any directory
# (the agent's working directory is usually the workspace, not the skill).
VENDORED_SKILL_ROOT = Path(__file__).resolve().parent.parent
CLI_HINT = "python3 " + shlex.quote(str(Path(__file__).resolve()))

# Sibling scripts import this file as `steer`; alias the module paths the
# package would provide so `from steer.output import ...` keeps working.
_self = sys.modules.get(__name__)
if _self is not None:
    sys.modules.setdefault("steer", _self)
    for _submodule in ({submodules}):
        sys.modules.setdefault(f"steer.{{_submodule}}", _self)

if __name__ == "__main__":
    sys.exit(runtime_main(
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
