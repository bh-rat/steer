"""
Packaging and installing skills.

`steer package` builds a Claude-API-ready zip (SKILL.md at the top of a
single root folder, junk excluded, 30MB limit enforced) after a
validation pass. `steer install` copies a skill directory or zip into a
project's or user's skills directory.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

from .paths import SKILL_FILE
from .skill import Skill, SkillNotFound
from .validate import Finding, has_errors, validate_skill

EXCLUDE_NAMES = {".DS_Store"}
EXCLUDE_DIRS = {".git", "__pycache__", ".steer", ".venv", "node_modules"}


class DistributeError(Exception):
    """Packaging or installation failed."""


def _included_files(skill_dir: Path) -> List[Path]:
    files = []
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(skill_dir)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if f.name in EXCLUDE_NAMES:
            continue
        files.append(f)
    return files


def package_skill(path, out: Optional[str] = None) -> Path:
    """Zip a validated skill. Returns the zip path.

    Raises DistributeError when validation finds errors (including
    packaging-escalated hygiene findings like credential files).
    """
    skill = Skill.load(path)  # raises SkillNotFound for bad paths
    findings = validate_skill(skill.path, for_packaging=True)
    if has_errors(findings):
        problems = "\n".join(f"  {f}" for f in findings if f.level == "error")
        raise DistributeError(
            f"Refusing to package '{skill.dir_name}'. Fix these first:\n{problems}"
        )

    out_path = Path(out).expanduser() if out else Path.cwd() / f"{skill.dir_name}.zip"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_out = out_path.resolve()
    own_zip = f"{skill.dir_name}.zip"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in _included_files(skill.path):
            # Packaging from inside the skill dir must not bundle the output
            # zip itself, nor a stale one from an earlier run.
            if f.resolve() == resolved_out or f.name == own_zip:
                continue
            arcname = f"{skill.dir_name}/{f.relative_to(skill.path)}"
            zf.write(f, arcname)
    return out_path


def _extract_zip_to_temp(zip_path: Path, temp_dir: str) -> Path:
    """Extract a skill zip and locate the directory holding SKILL.md."""
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = Path(temp_dir) / member
            if not target.resolve().is_relative_to(Path(temp_dir).resolve()):
                raise DistributeError(f"Unsafe path in zip: {member}")
        zf.extractall(temp_dir)
    root = Path(temp_dir)
    if (root / SKILL_FILE).is_file():
        return root
    candidates = [d for d in root.iterdir()
                  if d.is_dir() and (d / SKILL_FILE).is_file()]
    if len(candidates) != 1:
        raise DistributeError(
            f"{zip_path} does not contain exactly one skill folder with a "
            f"{SKILL_FILE}"
        )
    return candidates[0]


def install_skill(source, scope: str = "project", project_dir: str = ".",
                  dest_root: Optional[str] = None, force: bool = False) -> Path:
    """Install a skill (directory or zip) into a skills directory.

    Args:
        source: Skill directory or .zip file.
        scope: "project" (.claude/skills) or "user" (~/.claude/skills).
        project_dir: Project root for project scope.
        dest_root: Explicit skills root, overriding scope (e.g. a
            .agents/skills directory).
        force: Replace an existing installation.
    """
    src = Path(source).expanduser()

    with tempfile.TemporaryDirectory(prefix="steer-install-") as temp_dir:
        if src.is_file() and src.suffix == ".zip":
            skill_dir = _extract_zip_to_temp(src, temp_dir)
        elif src.is_dir():
            skill_dir = src
        else:
            raise DistributeError(f"Not a skill directory or zip: {src}")

        try:
            skill = Skill.load(skill_dir)
        except SkillNotFound as exc:
            raise DistributeError(str(exc)) from exc

        findings = validate_skill(skill.path)
        if has_errors(findings):
            problems = "\n".join(f"  {f}" for f in findings if f.level == "error")
            raise DistributeError(
                f"Refusing to install an invalid skill:\n{problems}"
            )

        if dest_root:
            root = Path(dest_root).expanduser()
        elif scope == "user":
            root = Path.home() / ".claude" / "skills"
        elif scope == "project":
            root = Path(project_dir).expanduser().resolve() / ".claude" / "skills"
        else:
            raise DistributeError(f"Unknown scope: {scope!r}")

        target = root / skill.dir_name
        if target.exists():
            if not force:
                raise DistributeError(
                    f"{target} already exists (use --force to replace)"
                )
            shutil.rmtree(target)
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            skill.path, target,
            ignore=shutil.ignore_patterns(*EXCLUDE_NAMES, *EXCLUDE_DIRS),
        )
    return target


def validation_summary_line(findings: List[Finding]) -> str:
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    if errors:
        return f"invalid ({len(errors)} error(s))"
    if warnings:
        return f"valid ({len(warnings)} warning(s))"
    return "valid"
