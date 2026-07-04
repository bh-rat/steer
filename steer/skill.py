"""
The Skill model: load, inspect, and discover Agent Skills.

A skill is a directory containing a SKILL.md file: YAML frontmatter
(name, description, and optional fields) followed by a markdown body.
This module is the shared representation used by validate, create,
distribute, and the runtime components.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .frontmatter import parse as parse_frontmatter
from .frontmatter import split_document
from .paths import SKILL_FILE, skill_search_roots

# Fields defined by the open Agent Skills spec (agentskills.io).
SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

# Claude Code frontmatter extensions: valid there, ignored elsewhere.
CLAUDE_CODE_FIELDS = {
    "when_to_use", "argument-hint", "arguments", "disable-model-invocation",
    "user-invocable", "disallowed-tools", "model", "effort", "context",
    "agent", "hooks", "paths", "shell",
}


class SkillNotFound(Exception):
    """Raised when a path does not contain a SKILL.md."""


@dataclass
class Skill:
    """A loaded skill directory."""
    path: Path                          # The skill directory
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    body: str = ""
    problems: List[str] = field(default_factory=list)  # frontmatter parse issues
    has_frontmatter: bool = True

    @property
    def name(self) -> str:
        value = self.frontmatter.get("name", "")
        return value if isinstance(value, str) else str(value)

    @property
    def description(self) -> str:
        value = self.frontmatter.get("description", "")
        return value if isinstance(value, str) else str(value)

    @property
    def dir_name(self) -> str:
        return self.path.name

    @property
    def version(self) -> Optional[str]:
        meta = self.frontmatter.get("metadata")
        if isinstance(meta, dict):
            version = meta.get("version")
            return str(version) if version is not None else None
        return None

    @property
    def skill_md(self) -> Path:
        return self.path / SKILL_FILE

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Skill":
        """Load a skill from a directory (or a direct path to SKILL.md)."""
        p = Path(path).expanduser()
        if p.is_file() and p.name == SKILL_FILE:
            p = p.parent
        skill_md = p / SKILL_FILE
        if not skill_md.is_file():
            raise SkillNotFound(f"No {SKILL_FILE} found in {p}")

        content = skill_md.read_text(encoding="utf-8")
        fm_text, body = split_document(content)
        if fm_text is None:
            return cls(path=p.resolve(), frontmatter={}, body=body,
                       problems=["missing frontmatter block (--- ... ---)"],
                       has_frontmatter=False)
        data, problems = parse_frontmatter(fm_text)
        return cls(path=p.resolve(), frontmatter=data, body=body, problems=problems)

    def files(self) -> List[Path]:
        """All files in the skill directory, junk excluded."""
        results = []
        for f in sorted(self.path.rglob("*")):
            if not f.is_file():
                continue
            parts = f.relative_to(self.path).parts
            if any(part in (".git", "__pycache__", ".steer", ".venv") for part in parts):
                continue
            if f.name == ".DS_Store":
                continue
            results.append(f)
        return results

    def total_size(self) -> int:
        return sum(f.stat().st_size for f in self.files())


def discover(project_dir: str = ".", roots: Optional[List[Path]] = None) -> List[Skill]:
    """Find installed skills across the standard search roots.

    Scans one directory level inside each root. On name collisions the
    earliest root wins (project scope shadows user scope, matching how
    agent products resolve them).
    """
    seen: Dict[str, Skill] = {}
    for root in roots if roots is not None else skill_search_roots(project_dir):
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not (child / SKILL_FILE).is_file():
                continue
            try:
                skill = Skill.load(child)
            except (OSError, SkillNotFound):
                continue
            key = skill.name or skill.dir_name
            if key not in seen:
                seen[key] = skill
    return list(seen.values())
