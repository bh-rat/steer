"""
Flow: enforced multi-step processes for skills.

Real skills fight step-skipping with ALL-CAPS prose ("You MUST complete
each phase before proceeding"). A Flow makes the process machine-checked
instead: a DAG of Steps, each with a verify function ("is this actually
done?") and a directive ("what to tell the agent next"). The agent only
ever sees the current step; later steps stay locked until reality says
their prerequisites are complete.

Two kinds of steps:
- **verified**: has a ``verify`` callable; completion is checked against
  reality (files exist, commands pass). The state file is never involved.
- **mandate**: no ``verify``; the agent (or human) marks it done
  explicitly; completion is recorded in ``<workspace>/.steer/flows/``.

Flows can be defined in Python or declaratively in a ``flow.toml``
shipped inside a skill (see ``load_flow``), which makes them usable from
a SKILL.md with no code at all:

    steer flow status      # progress + current directive
    steer flow next        # current directive only
    steer flow done <id>   # mark a mandate step complete
"""

import glob as glob_module
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .paths import workspace_steer_dir

_VERIFY_COMMAND_TIMEOUT = 60


class FlowBlockedError(Exception):
    """A step was acted on before its prerequisites were complete."""

    def __init__(self, step_id: str, unmet: List[str]):
        self.step_id = step_id
        self.unmet = unmet
        super().__init__(
            f"Step '{step_id}' is blocked. Complete these first: "
            f"{', '.join(unmet)}"
        )


class StepStatus(Enum):
    """Status of a step in a flow."""
    NOT_READY = "not_ready"      # Preconditions not met
    READY = "ready"              # Preconditions met, not yet complete
    COMPLETE = "complete"        # Step is done
    BLOCKED = "blocked"          # Cannot proceed (error or missing dependency)
    ERROR = "error"              # Step failed


@dataclass
class Directive:
    """Structured next-step instruction for an AI agent.

    A Directive tells the agent what to do next, what constraints apply,
    and what comes after. It can be serialized to JSON for programmatic
    consumption or rendered as human-readable text.
    """
    step: str                                           # Current step identifier
    status: StepStatus                                  # Current status
    action: Dict[str, Any] = field(default_factory=dict)  # What to do
    description: str = ""                               # Human-readable description
    constraints: List[Dict[str, str]] = field(default_factory=list)  # RFC 2119 constraints
    preconditions: List[str] = field(default_factory=list)           # Required conditions
    unmet_preconditions: List[str] = field(default_factory=list)     # Currently unmet
    effects: List[str] = field(default_factory=list)                 # Conditions set on completion
    next_step: Optional[str] = None                     # What comes after
    suggestions: List[str] = field(default_factory=list)  # Remediation hints (for errors)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (for JSON output / MCP structuredContent)."""
        result = {
            "step": self.step,
            "status": self.status.value,
            "description": self.description,
        }
        if self.action:
            result["action"] = self.action
        if self.constraints:
            result["constraints"] = self.constraints
        if self.preconditions:
            result["preconditions"] = self.preconditions
        if self.unmet_preconditions:
            result["unmet_preconditions"] = self.unmet_preconditions
        if self.effects:
            result["effects"] = self.effects
        if self.next_step:
            result["next"] = self.next_step
        if self.suggestions:
            result["suggestions"] = self.suggestions
        return result

    def to_human_readable(self) -> str:
        """Render as human-readable text."""
        lines = []
        lines.append(f"Step: {self.step}")
        lines.append(f"Status: {self.status.value}")
        if self.description:
            lines.append(f"Action: {self.description}")
        if self.unmet_preconditions:
            lines.append(f"Blocked by: {', '.join(self.unmet_preconditions)}")
        if self.next_step:
            lines.append(f"Next: {self.next_step}")
        if self.suggestions:
            lines.append("Suggestions:")
            for s in self.suggestions:
                lines.append(f"  - {s}")
        return "\n".join(lines)


@dataclass
class StepContext:
    """Context passed to step functions."""
    workspace: str
    config_dir: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    state: Dict[str, Any] = field(default_factory=dict)

    @property
    def completed(self) -> set:
        """Mandate steps that have been explicitly marked done."""
        return set(self.state.get("completed", []))

    def directive(self, description: str, command: str = "",
                  action_type: str = "command", **kwargs) -> Directive:
        """Helper to create a Directive from within a step function."""
        action = {"type": action_type, "description": description}
        if command:
            action["command"] = command
        return Directive(
            step=kwargs.get("step", ""),
            status=kwargs.get("status", StepStatus.READY),
            action=action,
            description=description,
            **{k: v for k, v in kwargs.items() if k not in ("step", "status")},
        )


@dataclass
class Step:
    """An atomic unit in a flow.

    Each step has:
    - id: unique identifier
    - description: what this step does
    - requires: list of step IDs that must be complete first
    - verify: function(ctx) -> bool, returns True if step is complete.
      When None, the step is a mandate step: completion comes from the
      persisted state (mark_complete / `steer flow done`).
    - get_directive: function(ctx) -> Directive, what to tell the agent
    """
    id: str
    description: str = ""
    requires: List[str] = field(default_factory=list)
    verify: Optional[Callable[[StepContext], bool]] = None
    get_directive: Optional[Callable[[StepContext], Directive]] = None
    tips: Optional[Callable[[StepContext], None]] = None

    def is_complete(self, ctx: StepContext) -> bool:
        """Check if this step is complete. Verify wins; statefile is the fallback."""
        if self.verify is not None:
            return self.verify(ctx)
        return self.id in ctx.completed


class Flow:
    """A DAG of Steps that guides an agent through a multi-step process.

    The flow inspects current state, walks the step DAG, and returns a
    Directive for the first step whose preconditions are met but isn't
    yet complete.

    Usage:
        flow = Flow("release", workspace=".")
        flow.add_step(Step(
            id="init",
            description="Initialize project",
            verify=lambda ctx: os.path.exists("settings.yaml"),
            get_directive=lambda ctx: ctx.directive(
                "Run 'my-tool init' to initialize", command="my-tool init",
            ),
        ))
        flow.add_step(Step(id="review", description="Review the plan",
                           requires=["init"]))  # mandate step

        directive = flow.get_directive(flow.context())
    """

    def __init__(self, name: str, workspace: str = ".",
                 context_factory: Optional[Callable] = None):
        """Create a Flow.

        Args:
            name: Flow name (used in rendering and the state file name).
            workspace: Default workspace path.
            context_factory: Optional callable (workspace, args=None) -> StepContext.
                Used by require_step() and after_step() to build context.
                If None, creates a StepContext with persisted state loaded.
        """
        self.name = name
        self.workspace = workspace
        self.context_factory = context_factory or self._default_context
        self._steps: Dict[str, Step] = {}
        self._order: List[str] = []  # Insertion order for deterministic traversal

    # -- state persistence (mandate steps) -----------------------------

    def _state_path(self, workspace: Optional[str] = None) -> Path:
        from .paths import checked_path_component

        ws = workspace or self.workspace
        name = checked_path_component(self.name, "flow")
        return workspace_steer_dir(ws) / "flows" / f"{name}.json"

    def load_state(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        path = self._state_path(workspace)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"completed": []}
        if not isinstance(data, dict):
            return {"completed": []}
        if not isinstance(data.get("completed"), list):
            data["completed"] = []
        return data

    def _save_state(self, state: Dict[str, Any], workspace: Optional[str] = None) -> None:
        path = self._state_path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        state["flow"] = self.name
        state["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def mark_complete(self, step_id: str, workspace: Optional[str] = None) -> bool:
        """Mark a mandate step as done (persisted). Returns False for
        verified steps; reality is their only source of truth.

        Raises FlowBlockedError when the step's prerequisites aren't
        complete: marking must not be a way to skip ahead.
        """
        step = self._steps.get(step_id)
        if step is None:
            raise ValueError(f"Unknown step: {step_id}")
        if step.verify is not None:
            return False
        ctx = self.context(workspace)
        unmet = self._get_unmet_prerequisites(step, ctx)
        if unmet:
            raise FlowBlockedError(step_id, unmet)
        state = self.load_state(workspace)
        completed = set(state.get("completed", []))
        completed.add(step_id)
        state["completed"] = sorted(completed)
        self._save_state(state, workspace)
        return True

    def reset(self, step_id: Optional[str] = None,
              workspace: Optional[str] = None) -> None:
        """Forget mandate-step completion (one step, or all when None)."""
        state = self.load_state(workspace)
        if step_id is None:
            state["completed"] = []
        else:
            state["completed"] = [s for s in state.get("completed", []) if s != step_id]
        self._save_state(state, workspace)

    def context(self, workspace: Optional[str] = None, args=None) -> StepContext:
        """Build a StepContext with persisted mandate state loaded."""
        ws = workspace or self.workspace
        ctx = self.context_factory(ws, args)
        ctx.state.setdefault("completed", self.load_state(ws).get("completed", []))
        return ctx

    def _default_context(self, workspace: str, args=None) -> StepContext:
        return StepContext(workspace=workspace)

    # -- step registration ---------------------------------------------

    def add_step(self, step: Step) -> None:
        """Add a step to the flow."""
        if step.id in self._steps:
            raise ValueError(f"Duplicate step ID: {step.id}")
        self._steps[step.id] = step
        self._order.append(step.id)

    def step(self, step_id: str, requires: Optional[List[str]] = None,
             description: str = ""):
        """Decorator to register a step function as its directive."""
        def decorator(fn):
            s = Step(
                id=step_id,
                description=description or fn.__doc__ or "",
                requires=requires or [],
                get_directive=fn,
            )
            self.add_step(s)
            return fn
        return decorator

    @property
    def steps(self) -> List[Step]:
        """All steps in insertion order."""
        return [self._steps[sid] for sid in self._order]

    def get_step(self, step_id: str) -> Optional[Step]:
        """Get a step by ID."""
        return self._steps.get(step_id)

    # -- DAG walking -----------------------------------------------------

    def _prerequisites_met(self, step: Step, ctx: StepContext) -> bool:
        for req_id in step.requires:
            req_step = self._steps.get(req_id)
            if req_step is None:
                return False  # Missing dependency
            if not req_step.is_complete(ctx):
                return False
        return True

    def _get_unmet_prerequisites(self, step: Step, ctx: StepContext) -> List[str]:
        unmet = []
        for req_id in step.requires:
            req_step = self._steps.get(req_id)
            if req_step is None or not req_step.is_complete(ctx):
                unmet.append(req_id)
        return unmet

    def get_current_step(self, ctx: StepContext) -> Optional[Step]:
        """Find the first step whose prerequisites are met but isn't complete."""
        for step_id in self._order:
            step = self._steps[step_id]
            if step.is_complete(ctx):
                continue
            if self._prerequisites_met(step, ctx):
                return step
        return None  # All steps complete or blocked

    def get_directive(self, ctx: Optional[StepContext] = None) -> Optional[Directive]:
        """Get the directive for the current step.

        Walks the DAG, finds the first actionable step, and returns its
        directive. Returns a COMPLETE directive when everything is done.
        """
        if ctx is None:
            ctx = self.context()

        current = self.get_current_step(ctx)
        if current is None:
            all_complete = all(s.is_complete(ctx) for s in self.steps)
            if all_complete:
                return Directive(
                    step="complete",
                    status=StepStatus.COMPLETE,
                    description="All steps complete.",
                )
            for step_id in self._order:
                step = self._steps[step_id]
                if not step.is_complete(ctx):
                    unmet = self._get_unmet_prerequisites(step, ctx)
                    return Directive(
                        step=step.id,
                        status=StepStatus.BLOCKED,
                        description=f"Step '{step.id}' is blocked.",
                        unmet_preconditions=unmet,
                    )
            return None

        if current.get_directive:
            directive = current.get_directive(ctx)
            if not directive.step:
                directive.step = current.id
            current_idx = self._order.index(current.id)
            if current_idx + 1 < len(self._order):
                directive.next_step = self._order[current_idx + 1]
            return directive

        # No directive function; return a generic one
        mandate_hint = ""
        if current.verify is None:
            mandate_hint = (f" When finished, mark it done: "
                            f"steer flow done {current.id}")
        return Directive(
            step=current.id,
            status=StepStatus.READY,
            description=(current.description or f"Complete step '{current.id}'")
                        + mandate_hint,
        )

    # -- gating and nudging ----------------------------------------------

    def gate(self, step_id: str, ctx: StepContext) -> bool:
        """Check if a step's prerequisites are met. If not, print what's needed.

        Use this at the top of command implementations for step gating.
        Returns True if the step can run, False if blocked.
        """
        step = self._steps.get(step_id)
        if step is None:
            return True  # Unknown step, let it run

        unmet = self._get_unmet_prerequisites(step, ctx)
        if not unmet:
            return True

        from .renderer import render_directive

        first_unmet_id = unmet[0]
        first_unmet = self._steps.get(first_unmet_id)

        print()
        print(f"  Not ready: '{step_id}' requires "
              f"'{first_unmet_id}' to be completed first.")
        print()

        if first_unmet and first_unmet.get_directive:
            directive = first_unmet.get_directive(ctx)
            if not directive.step:
                directive.step = first_unmet_id
            render_directive(directive)

        return False

    def nudge(self, completed_step_id: str, ctx: StepContext) -> None:
        """After a command completes, show what to do next."""
        step = self._steps.get(completed_step_id)
        if step is None:
            return

        if completed_step_id in self._order:
            idx = self._order.index(completed_step_id)
            for next_id in self._order[idx + 1:]:
                next_step = self._steps[next_id]
                if not next_step.is_complete(ctx):
                    if self._prerequisites_met(next_step, ctx):
                        print()
                        print("  ▸ Next step")
                        if next_step.get_directive:
                            directive = next_step.get_directive(ctx)
                            if not directive.step:
                                directive.step = next_id
                            action = directive.action
                            if action.get('command'):
                                print(f"    Run: {action['command']}")
                            print(f"    {directive.description}")
                        else:
                            print(f"    {next_step.description}")
                        print()
                    return

    def get_progress(self, ctx: Optional[StepContext] = None) -> Dict[str, Any]:
        """Get flow progress summary."""
        if ctx is None:
            ctx = self.context()

        total = len(self._order)
        completed = sum(1 for s in self.steps if s.is_complete(ctx))
        current = self.get_current_step(ctx)

        return {
            "flow": self.name,
            "total_steps": total,
            "completed_steps": completed,
            "current_step": current.id if current else None,
            "progress_pct": (completed / total * 100) if total > 0 else 100,
            "steps": [
                {
                    "id": s.id,
                    "description": s.description,
                    "status": "complete" if s.is_complete(ctx)
                             else "ready" if self._prerequisites_met(s, ctx)
                             else "not_ready",
                }
                for s in self.steps
            ],
        }

    def require_step(self, step_id: str, args=None) -> StepContext:
        """Gate a command: check prerequisites, exit if not met."""
        ctx = self.context(args=args)
        if not self.gate(step_id, ctx):
            sys.exit(1)
        return ctx

    def after_step(self, step_id: str, ctx: StepContext) -> None:
        """Show next-step guidance after a command completes."""
        ctx_fresh = self.context(ctx.workspace)
        self.nudge(step_id, ctx_fresh)


# -- declarative flows (flow.toml) ----------------------------------------

def _make_verifier(conditions: Dict[str, Any], flow_dir: Path) -> Callable[[StepContext], bool]:
    """Build a verify callable from a [steps.verify] table.

    Supported conditions (all must pass):
        file_exists = "path"        relative to the workspace
        dir_exists = "path"
        glob = "pattern"            at least one match
        command = "shell command"   exit code 0 means complete
        env = "VAR_NAME"            variable is set and non-empty
    """
    known = {"file_exists", "dir_exists", "glob", "command", "env"}
    unknown = set(conditions) - known
    if unknown:
        raise ValueError(f"Unknown verify conditions: {', '.join(sorted(unknown))}")

    def verify(ctx: StepContext) -> bool:
        ws = Path(ctx.workspace).expanduser()
        if "file_exists" in conditions:
            if not (ws / str(conditions["file_exists"])).is_file():
                return False
        if "dir_exists" in conditions:
            if not (ws / str(conditions["dir_exists"])).is_dir():
                return False
        if "glob" in conditions:
            pattern = str(ws / str(conditions["glob"]))
            if not glob_module.glob(pattern, recursive=True):
                return False
        if "env" in conditions:
            if not os.environ.get(str(conditions["env"])):
                return False
        if "command" in conditions:
            try:
                proc = subprocess.run(
                    str(conditions["command"]), shell=True, cwd=str(ws),
                    capture_output=True, timeout=_VERIFY_COMMAND_TIMEOUT,
                )
            except (OSError, subprocess.TimeoutExpired):
                return False
            if proc.returncode != 0:
                return False
        return True

    return verify


def _make_declarative_directive(spec: Dict[str, Any]) -> Callable[[StepContext], Directive]:
    description = str(spec.get("directive", "") or spec.get("description", ""))
    command = str(spec.get("command", ""))

    def get_directive(ctx: StepContext) -> Directive:
        action: Dict[str, Any] = {
            "type": "command" if command else "instruction",
            "description": description,
        }
        if command:
            action["command"] = command
        return Directive(
            step=str(spec["id"]),
            status=StepStatus.READY,
            description=description,
            action=action,
        )

    return get_directive


def load_flow(path, workspace: str = ".") -> Flow:
    """Load a declarative flow from a flow.toml file.

    Schema:
        name = "release"              # optional, defaults to file stem
        description = "..."           # optional

        [[steps]]
        id = "init"
        description = "Initialize the workspace"
        directive = "Run `mytool init` in the workspace root"
        command = "mytool init"       # optional suggested command
        requires = []                 # optional step dependencies
        [steps.verify]                # optional; omit -> mandate step
        file_exists = "settings.yaml"
    """
    toml_path = Path(path).expanduser()
    if toml_path.is_dir():
        toml_path = toml_path / "flow.toml"
    if not toml_path.is_file():
        raise FileNotFoundError(f"Flow file not found: {toml_path}")

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    # Installed skills run with the workspace as cwd, so a directive's
    # `scripts/...` would not resolve verbatim. flow.toml strings may use
    # {skill_dir} (the flow file's directory) and {workspace}; agents can
    # then execute the printed command exactly as shown.
    def expand(text: str) -> str:
        return (text
                .replace("{skill_dir}", str(toml_path.parent.resolve()))
                .replace("{workspace}",
                         str(Path(workspace).expanduser().resolve())))

    name = str(data.get("name") or toml_path.stem)
    flow = Flow(name, workspace=workspace)

    steps = data.get("steps", [])
    if not steps:
        raise ValueError(f"{toml_path}: flow has no [[steps]]")
    for spec in steps:
        if "id" not in spec:
            raise ValueError(f"{toml_path}: every [[steps]] entry needs an 'id'")
        for key in ("directive", "command"):
            if isinstance(spec.get(key), str):
                spec[key] = expand(spec[key])
        verify_spec = spec.get("verify")
        if verify_spec:
            verify_spec = {k: expand(v) if isinstance(v, str) else v
                           for k, v in verify_spec.items()}
        verify = _make_verifier(verify_spec, toml_path.parent) if verify_spec else None
        requires = spec.get("requires", [])
        if isinstance(requires, str):
            requires = [requires]
        flow.add_step(Step(
            id=str(spec["id"]),
            description=str(spec.get("description", "")),
            requires=[str(r) for r in requires],
            verify=verify,
            get_directive=_make_declarative_directive(spec),
        ))
    return flow


def find_flow_file(skill_dir) -> Optional[Path]:
    """Locate a skill's flow definition: flow.toml at the skill root,
    or the first file in flows/*.toml."""
    root = Path(skill_dir).expanduser()
    direct = root / "flow.toml"
    if direct.is_file():
        return direct
    flows_dir = root / "flows"
    if flows_dir.is_dir():
        candidates = sorted(flows_dir.glob("*.toml"))
        if candidates:
            return candidates[0]
    return None
