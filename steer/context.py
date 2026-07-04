"""
Context gathering: one call that answers "where am I, what is this
project, what can I use here?"

Every serious skill starts with a hand-rolled "figure out the situation"
preamble: git probes, marker-file checks, `command -v` ladders,
host-agent detection. Steer turns that into a single snapshot, available
as markdown (for the agent to read) or JSON (for scripts).

Sections: system, agent, git, project, tools, env.

Usage:
    from steer.context import gather, to_markdown
    snapshot = gather()                  # all sections
    print(to_markdown(snapshot))

CLI:
    steer context                # markdown
    steer context --json
    steer context --only git,project
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SECTIONS = ("system", "agent", "git", "project", "tools", "env")

# Binaries worth knowing about, probed on PATH.
DEFAULT_TOOLS = [
    "git", "gh", "docker", "node", "npm", "pnpm", "yarn", "bun", "deno",
    "python3", "uv", "pip3", "pipx", "cargo", "go", "make", "cmake",
    "jq", "rg", "curl", "sqlite3", "psql", "kubectl", "terraform",
]

# Environment markers for the agent hosting this process.
_AGENT_MARKERS = [
    ("CLAUDECODE", "claude-code"),
    ("CLAUDE_CODE_ENTRYPOINT", "claude-code"),
    ("CODEX_CI", "openai-codex"),
    ("CODEX_HOME", "openai-codex"),
    ("CURSOR_TRACE_ID", "cursor"),
    ("GEMINI_CLI", "gemini-cli"),
    ("GITHUB_COPILOT_AGENT", "github-copilot"),
    ("AMP_SESSION_ID", "amp"),
    ("GOOSE_SESSION", "goose"),
]

# Project marker files -> what they indicate.
_PROJECT_MARKERS = [
    ("package.json", "node"),
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("setup.py", "python"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
    ("Gemfile", "ruby"),
    ("pom.xml", "java-maven"),
    ("build.gradle", "java-gradle"),
    ("build.gradle.kts", "java-gradle"),
    ("mix.exs", "elixir"),
    ("composer.json", "php"),
]

_PACKAGE_MANAGER_LOCKS = [
    ("uv.lock", "uv"),
    ("poetry.lock", "poetry"),
    ("Pipfile.lock", "pipenv"),
    ("package-lock.json", "npm"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
]

_EXTRA_MARKERS = [
    ("Dockerfile", "docker"),
    ("docker-compose.yml", "docker-compose"),
    ("docker-compose.yaml", "docker-compose"),
    ("Makefile", "make"),
    (".github/workflows", "github-actions"),
    (".gitlab-ci.yml", "gitlab-ci"),
    ("SKILL.md", "agent-skill"),
]

# Safe-to-report environment variables (never dump the environment).
_ENV_ALLOWLIST = ["CI", "TERM", "LANG", "SHELL", "VIRTUAL_ENV", "NODE_ENV"]

_GIT_TIMEOUT = 5


def _git(args: List[str], cwd: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.rstrip("\n")


def _gather_system() -> Dict[str, Any]:
    return {
        "os": platform.system(),
        "release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
    }


def _gather_agent() -> Dict[str, Any]:
    detected = "unknown"
    for env_var, agent_name in _AGENT_MARKERS:
        if os.environ.get(env_var):
            detected = agent_name
            break
    return {
        "host_agent": detected,
        "is_ci": bool(os.environ.get("CI")),
        "is_tty": sys.stdout.isatty(),
    }


def _gather_git(workspace: str) -> Dict[str, Any]:
    if shutil.which("git") is None:
        return {"available": False}
    inside = _git(["rev-parse", "--is-inside-work-tree"], workspace)
    if inside != "true":
        return {"available": True, "in_repo": False}

    info: Dict[str, Any] = {"available": True, "in_repo": True}
    info["branch"] = _git(["rev-parse", "--abbrev-ref", "HEAD"], workspace)
    status = _git(["status", "--porcelain"], workspace)
    lines = [ln for ln in (status or "").splitlines() if ln.strip()]
    info["dirty_files"] = len(lines)
    info["untracked_files"] = len([ln for ln in lines if ln.startswith("??")])
    log = _git(["log", "--oneline", "-3"], workspace)
    info["recent_commits"] = (log or "").splitlines()
    remotes = _git(["remote"], workspace)
    info["remotes"] = (remotes or "").splitlines()
    git_dir = _git(["rev-parse", "--git-dir"], workspace)
    common_dir = _git(["rev-parse", "--git-common-dir"], workspace)
    info["is_linked_worktree"] = bool(
        git_dir and common_dir and git_dir != common_dir
    )
    return info


def _gather_project(workspace: str) -> Dict[str, Any]:
    root = Path(workspace).expanduser()
    types: List[str] = []
    markers: List[str] = []
    package_managers: List[str] = []

    for marker, kind in _PROJECT_MARKERS:
        if (root / marker).exists():
            markers.append(marker)
            if kind not in types:
                types.append(kind)
    for lock, manager in _PACKAGE_MANAGER_LOCKS:
        if (root / lock).exists() and manager not in package_managers:
            package_managers.append(manager)
    extras = [name for marker, name in _EXTRA_MARKERS if (root / marker).exists()]

    return {
        "types": types,
        "package_managers": package_managers,
        "markers": markers,
        "extras": extras,
    }


def _gather_tools(extra: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    names = list(DEFAULT_TOOLS)
    for name in extra or []:
        if name and name not in names:
            names.append(name)
    available = [name for name in names if shutil.which(name)]
    missing = [name for name in names if name not in available]
    return {"available": available, "missing": missing}


def _gather_env() -> Dict[str, Any]:
    return {name: os.environ[name] for name in _ENV_ALLOWLIST if os.environ.get(name)}


def gather(workspace: str = ".", only: Optional[Iterable[str]] = None,
           tools: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Collect a context snapshot.

    Args:
        workspace: Directory to inspect (git/project sections).
        only: Optional subset of SECTIONS to collect.
        tools: Extra binary names to probe in the tools section.
    """
    wanted = list(only) if only else list(SECTIONS)
    unknown = [s for s in wanted if s not in SECTIONS]
    if unknown:
        raise ValueError(f"Unknown context sections: {', '.join(unknown)}")

    snapshot: Dict[str, Any] = {}
    if "system" in wanted:
        snapshot["system"] = _gather_system()
    if "agent" in wanted:
        snapshot["agent"] = _gather_agent()
    if "git" in wanted:
        snapshot["git"] = _gather_git(workspace)
    if "project" in wanted:
        snapshot["project"] = _gather_project(workspace)
    if "tools" in wanted:
        snapshot["tools"] = _gather_tools(tools)
    if "env" in wanted:
        snapshot["env"] = _gather_env()
    return snapshot


def to_markdown(snapshot: Dict[str, Any]) -> str:
    """Render a snapshot as compact markdown for an agent to read."""
    lines: List[str] = ["## Context snapshot"]

    system = snapshot.get("system")
    if system:
        lines.append(
            f"- **System**: {system['os']} {system['arch']}, "
            f"Python {system['python']}, cwd `{system['cwd']}`"
        )
    agent = snapshot.get("agent")
    if agent:
        flags = []
        if agent.get("is_ci"):
            flags.append("CI")
        if not agent.get("is_tty"):
            flags.append("non-interactive")
        suffix = f" ({', '.join(flags)})" if flags else ""
        lines.append(f"- **Host agent**: {agent['host_agent']}{suffix}")

    git = snapshot.get("git")
    if git:
        if not git.get("available"):
            lines.append("- **Git**: not installed")
        elif not git.get("in_repo"):
            lines.append("- **Git**: not a repository")
        else:
            worktree = ", linked worktree" if git.get("is_linked_worktree") else ""
            lines.append(
                f"- **Git**: branch `{git.get('branch')}`, "
                f"{git.get('dirty_files', 0)} dirty files"
                f" ({git.get('untracked_files', 0)} untracked){worktree}"
            )
            for commit in git.get("recent_commits", []):
                lines.append(f"  - `{commit}`")

    project = snapshot.get("project")
    if project:
        types = ", ".join(project["types"]) or "none detected"
        lines.append(f"- **Project**: {types}")
        if project["package_managers"]:
            lines.append(f"  - package managers: {', '.join(project['package_managers'])}")
        if project["extras"]:
            lines.append(f"  - also present: {', '.join(project['extras'])}")

    tools = snapshot.get("tools")
    if tools:
        lines.append(f"- **Tools on PATH**: {', '.join(tools['available'])}")
        if tools["missing"]:
            lines.append(f"  - missing: {', '.join(tools['missing'])}")

    env = snapshot.get("env")
    if env:
        pairs = ", ".join(f"{k}={v}" for k, v in env.items())
        lines.append(f"- **Env**: {pairs}")

    return "\n".join(lines)
