"""
Steer: the framework for building Agent Skills.

Skills (SKILL.md + scripts/references/assets) ship with no batteries:
the spec says nothing about credentials, persistence, context gathering,
or step enforcement. Steer provides those as components, plus the
authoring tools to scaffold, validate, package, and install skills.

Author-time (CLI):
    steer new my-skill --with secrets,store,context,flow
    steer validate            steer package
    steer install             steer list

Runtime (library or CLI, usable from SKILL.md with no code):
    from steer import Secrets, Store, Flow, Step
    from steer.context import gather
    from steer.output import print_envelope

Skills scaffolded with components carry the runtime with them: `steer
new` writes a self-contained scripts/steer.py holding exactly the chosen
components (see vendor.py), so running such a skill needs Python, not a
steer install.

Steer is zero-dependency: Python stdlib only.
"""

__version__ = "0.1.1"

from .flow import (
    Directive,
    Flow,
    FlowBlockedError,
    Step,
    StepContext,
    StepStatus,
    load_flow,
)
from .learn import Learnings, LessonRejected
from .output import envelope, output_json, print_envelope
from .renderer import render_commands, render_directive, render_workflow
from .scaffold import FileSpec, ScaffoldResult, scaffold_project
from .secrets import MissingSecretError, Secrets
from .skill import Skill, SkillNotFound, discover
from .store import Store
from .validate import Finding, validate_skill

__all__ = [
    "__version__",
    # flow
    "Flow", "FlowBlockedError", "Step", "Directive", "StepContext",
    "StepStatus", "load_flow",
    # components
    "Secrets", "MissingSecretError", "Store", "Learnings", "LessonRejected",
    # skill model + authoring
    "Skill", "SkillNotFound", "discover", "Finding", "validate_skill",
    "scaffold_project", "FileSpec", "ScaffoldResult",
    # output
    "envelope", "print_envelope", "output_json",
    "render_workflow", "render_directive", "render_commands",
]
