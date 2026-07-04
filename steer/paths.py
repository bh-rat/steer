"""
Path conventions for steer.

Steer keeps all of its own data under a single home directory
(``~/.steer`` by default, overridable with ``STEER_HOME``). Each skill
gets a private data directory for its store and file-backed secrets.

Workspace-scoped data (flow state, workspace stores) lives under
``<workspace>/.steer/`` so it travels with the project being operated on.
"""

import os
import re
from pathlib import Path
from typing import List, Optional

STEER_HOME_ENV = "STEER_HOME"
SKILL_ENV = "STEER_SKILL"
SKILL_FILE = "SKILL.md"

# The open spec's name rule (also what makes a name a safe directory name).
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SKILL_NAME_MAX = 64

# Flow/process names: looser than skill names, but still a single safe
# path component (no separators, no dot-files, no traversal).
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def checked_skill_name(name: str) -> str:
    """Validate a skill name before it becomes a filesystem path.

    Skill names turn into directories under ~/.steer and
    <workspace>/.steer, and the name can come from a third-party
    SKILL.md's frontmatter. Enforcing the spec's kebab-case rule here
    stops a hostile `name: ../../x` from escaping steer's data dirs.
    """
    if (not name or not isinstance(name, str)
            or len(name) > SKILL_NAME_MAX or not SKILL_NAME_RE.match(name)):
        raise ValueError(
            f"Invalid skill name {name!r}: must be lowercase kebab-case "
            f"(letters, digits, single hyphens; max {SKILL_NAME_MAX} chars). "
            f"Fix the 'name' in SKILL.md, or pass --skill <valid-name>."
        )
    return name


def checked_path_component(name: str, what: str) -> str:
    """Validate a user-supplied name used as a single path component."""
    if not name or not isinstance(name, str) or not _COMPONENT_RE.match(name):
        raise ValueError(
            f"Invalid {what} name {name!r}: use letters, digits, dots, "
            f"hyphens, or underscores (must not start with a dot; max 64 "
            f"chars)."
        )
    return name


def steer_home() -> Path:
    """Steer's own data directory (~/.steer or $STEER_HOME)."""
    override = os.environ.get(STEER_HOME_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".steer"


def skill_data_dir(skill_name: str, create: bool = False) -> Path:
    """Private data directory for a skill (store.db, secrets.json)."""
    path = steer_home() / "skills" / checked_skill_name(skill_name)
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def workspace_steer_dir(workspace: str = ".", create: bool = False) -> Path:
    """Workspace-scoped steer directory (<workspace>/.steer)."""
    path = Path(workspace).expanduser().resolve() / ".steer"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def find_skill_root(start: str = ".") -> Optional[Path]:
    """Walk upward from `start` looking for a directory containing SKILL.md.

    Lets `steer` CLI commands infer which skill they're operating on when
    run from inside a skill directory.
    """
    current = Path(start).expanduser().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / SKILL_FILE).is_file():
            return candidate
    return None


def infer_skill_name(explicit: Optional[str] = None, start: str = ".") -> Optional[str]:
    """Resolve the skill name a command should operate on.

    Resolution order: explicit --skill flag, STEER_SKILL env var,
    nearest SKILL.md frontmatter name (falling back to its directory name).
    """
    if explicit:
        return explicit
    env_name = os.environ.get(SKILL_ENV)
    if env_name:
        return env_name
    root = find_skill_root(start)
    if root is not None:
        from .skill import Skill  # late import to avoid a cycle

        skill = Skill.load(root)
        if skill.name:
            return skill.name
        return root.name
    return None


def skill_search_roots(project_dir: str = ".") -> List[Path]:
    """Directories that agent products scan for installed skills.

    Covers the cross-client ``.agents/skills`` convention from the open
    Agent Skills standard plus the Claude Code native locations, at both
    project and user scope. Project paths come first (project overrides
    user on name collisions, per the spec's client guidance).
    """
    project = Path(project_dir).expanduser().resolve()
    return [
        project / ".claude" / "skills",
        project / ".agents" / "skills",
        Path.home() / ".claude" / "skills",
        Path.home() / ".agents" / "skills",
    ]
