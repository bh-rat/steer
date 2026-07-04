"""
Skill validation: the open Agent Skills spec, portability, and hygiene.

Goes beyond structural frontmatter checks: broken references, body
budgets that break progressive disclosure, descriptions too thin to
trigger, Claude-Code-only fields that won't port, and (because skill
directories get zipped and uploaded) credential files that must never
ship inside a skill.

Usage:
    from steer.validate import validate_skill
    findings = validate_skill("./my-skill")
    errors = [f for f in findings if f.level == "error"]
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .paths import SKILL_NAME_MAX as NAME_MAX
from .paths import SKILL_NAME_RE as NAME_PATTERN
from .skill import CLAUDE_CODE_FIELDS, SPEC_FIELDS, Skill, SkillNotFound

ERROR = "error"
WARNING = "warning"
INFO = "info"

XML_TAG = re.compile(r"<[a-zA-Z/!][^>]*>")
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500
BODY_LINE_BUDGET = 500          # spec guidance: keep SKILL.md under 500 lines
BODY_TOKEN_BUDGET = 5000        # ~tokens, estimated at 4 chars/token
SIZE_WARN_BYTES = 10 * 1024 * 1024
SIZE_MAX_BYTES = 30 * 1024 * 1024  # Claude API zip upload limit

# Files that suggest credentials living inside the skill directory.
SECRET_FILE_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*_rsa", "*_ed25519",
    "credentials*.json", "secrets.*", "*.keystore", "*token*.json",
]

_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")
_RESOURCE_MENTION = re.compile(r"`((?:scripts|references|assets)/[^`\s]+)`")


@dataclass
class Finding:
    """One validation result."""
    level: str        # error | warning | info
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def validate_skill(path, for_packaging: bool = False) -> List[Finding]:
    """Validate a skill directory. Returns findings; empty means clean.

    Args:
        path: Skill directory (or SKILL.md path).
        for_packaging: Escalate ship-blocking hygiene issues (credential
            files, >30MB) to errors.
    """
    findings: List[Finding] = []
    try:
        skill = Skill.load(path)
    except SkillNotFound as exc:
        return [Finding(ERROR, "SKILL_MISSING", str(exc))]

    for problem in skill.problems:
        level = ERROR if not skill.has_frontmatter else WARNING
        findings.append(Finding(level, "FRONTMATTER_PARSE", problem))

    findings.extend(_check_name(skill))
    findings.extend(_check_description(skill))
    findings.extend(_check_optional_fields(skill))
    findings.extend(_check_unknown_fields(skill))
    findings.extend(_check_body(skill))
    findings.extend(_check_references(skill))
    findings.extend(_check_orphan_references(skill))
    findings.extend(_check_duplication(skill))
    findings.extend(_check_scripts(skill))
    findings.extend(_check_runtime(skill, for_packaging))
    findings.extend(_check_learnings(skill))
    findings.extend(_check_hygiene(skill, for_packaging))
    return findings


def _model_invocation_disabled(skill: Skill) -> bool:
    return skill.frontmatter.get("disable-model-invocation") is True


def _check_name(skill: Skill) -> List[Finding]:
    findings = []
    name = skill.frontmatter.get("name")
    if not name or not isinstance(name, str):
        findings.append(Finding(ERROR, "NAME_MISSING",
                                "frontmatter must include a 'name'"))
        return findings
    if len(name) > NAME_MAX:
        findings.append(Finding(ERROR, "NAME_TOO_LONG",
                                f"name is {len(name)} chars (max {NAME_MAX})"))
    if not NAME_PATTERN.match(name):
        findings.append(Finding(
            ERROR, "NAME_INVALID",
            f"name {name!r} must be lowercase letters/digits with single "
            f"hyphens (no leading/trailing/consecutive hyphens)"))
    if name != skill.dir_name:
        findings.append(Finding(
            ERROR, "NAME_DIR_MISMATCH",
            f"name {name!r} must match the directory name {skill.dir_name!r} "
            f"(the spec requires it; several clients key invocation off the "
            f"directory)"))
    lowered = name.lower()
    if "claude" in lowered or "anthropic" in lowered:
        findings.append(Finding(
            WARNING, "NAME_RESERVED",
            "names containing 'claude' or 'anthropic' are rejected by the "
            "Claude API skill upload"))
    if XML_TAG.search(name):
        findings.append(Finding(ERROR, "NAME_XML",
                                "name must not contain XML tags"))
    return findings


def _check_description(skill: Skill) -> List[Finding]:
    findings = []
    description = skill.frontmatter.get("description")
    if not description or not isinstance(description, str) or not description.strip():
        findings.append(Finding(ERROR, "DESC_MISSING",
                                "frontmatter must include a non-empty 'description'"))
        return findings
    description = description.strip()
    if len(description) > DESCRIPTION_MAX:
        findings.append(Finding(
            ERROR, "DESC_TOO_LONG",
            f"description is {len(description)} chars (max {DESCRIPTION_MAX})"))
    if XML_TAG.search(description):
        findings.append(Finding(ERROR, "DESC_XML",
                                "description must not contain XML tags"))
    if _model_invocation_disabled(skill):
        # User-invoked skill: the description is for the human's skill
        # list, not the trigger. Trigger-shape checks don't apply.
        return findings
    if len(description) < 40:
        findings.append(Finding(
            WARNING, "DESC_THIN",
            f"description is only {len(description)} chars, too thin to "
            f"trigger reliably. Say what the skill does AND when to use it."))
    elif not re.search(r"\b([Uu]se (this |it )?when|[Ww]hen (the user|you|asked)|[Ff]or )",
                       description):
        findings.append(Finding(
            INFO, "DESC_NO_TRIGGER",
            "description doesn't state when to use the skill. Trigger "
            "phrasing ('Use when ...') is the main lever for reliable "
            "activation"))
    return findings


def _check_optional_fields(skill: Skill) -> List[Finding]:
    findings = []
    compatibility = skill.frontmatter.get("compatibility")
    if isinstance(compatibility, str) and len(compatibility) > COMPATIBILITY_MAX:
        findings.append(Finding(
            WARNING, "COMPAT_TOO_LONG",
            f"compatibility is {len(compatibility)} chars (max {COMPATIBILITY_MAX})"))
    metadata = skill.frontmatter.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            findings.append(Finding(WARNING, "METADATA_NOT_MAP",
                                    "metadata should be a map of string keys to string values"))
        else:
            bad = [k for k, v in metadata.items() if not isinstance(v, (str, bool, int, float))]
            if bad:
                findings.append(Finding(
                    WARNING, "METADATA_VALUES",
                    f"metadata values should be strings (spec): {', '.join(bad)}"))
            if "version" not in metadata:
                findings.append(Finding(
                    INFO, "NO_VERSION",
                    "consider metadata.version, the ecosystem convention for "
                    "skill versioning"))
    else:
        findings.append(Finding(
            INFO, "NO_VERSION",
            "consider metadata.version, the ecosystem convention for skill "
            "versioning"))
    return findings


def _check_unknown_fields(skill: Skill) -> List[Finding]:
    findings = []
    for key in skill.frontmatter:
        if key in SPEC_FIELDS:
            continue
        if key == "disable-model-invocation":
            findings.append(Finding(
                INFO, "PORTABILITY",
                "'disable-model-invocation' is a Claude Code extension; "
                "other agents may still auto-trigger this skill off its "
                "description"))
        elif key in CLAUDE_CODE_FIELDS:
            findings.append(Finding(
                WARNING, "PORTABILITY",
                f"'{key}' is a Claude Code extension. Other agents ignore it; "
                f"make sure the skill degrades gracefully without it"))
        else:
            findings.append(Finding(
                WARNING, "UNKNOWN_FIELD",
                f"'{key}' is not a spec or Claude Code field; clients will "
                f"ignore it (custom data belongs under 'metadata')"))
    return findings


def _check_body(skill: Skill) -> List[Finding]:
    findings = []
    if not skill.body.strip():
        findings.append(Finding(WARNING, "BODY_EMPTY",
                                "SKILL.md has no body: nothing for the agent "
                                "to follow once triggered"))
        return findings
    line_count = len(skill.body.splitlines())
    if line_count > BODY_LINE_BUDGET:
        findings.append(Finding(
            WARNING, "BODY_LONG",
            f"body is {line_count} lines (guidance: <{BODY_LINE_BUDGET}). "
            f"Move detail into references/; it loads on demand"))
    tokens = _estimate_tokens(skill.body)
    if tokens > BODY_TOKEN_BUDGET:
        findings.append(Finding(
            WARNING, "BODY_TOKENS",
            f"body is ~{tokens} tokens (guidance: <{BODY_TOKEN_BUDGET}); the "
            f"whole body enters context on every trigger"))
    return findings


def _check_references(skill: Skill) -> List[Finding]:
    findings = []
    seen = set()
    candidates = []
    for match in _MD_LINK.finditer(skill.body):
        candidates.append((match.group(1), ERROR, "LINK_BROKEN"))
    for match in _RESOURCE_MENTION.finditer(skill.body):
        candidates.append((match.group(1), WARNING, "RESOURCE_MISSING"))

    for raw, level, code in candidates:
        target = raw.strip()
        if re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
            continue
        target = target.split("#")[0].strip()
        if not target or target in seen:
            continue
        seen.add(target)
        if not (skill.path / target).exists():
            findings.append(Finding(
                level, code,
                f"SKILL.md references '{target}' but it doesn't exist in the "
                f"skill directory"))
    return findings


_REFERENCE_EXTS = {".md", ".mdx", ".txt"}


def _reference_files(skill: Skill) -> List[Path]:
    ref_dir = skill.path / "references"
    if not ref_dir.is_dir():
        return []
    return [f for f in sorted(ref_dir.rglob("*"))
            if f.is_file() and f.name != ".DS_Store"]


def _check_orphan_references(skill: Skill) -> List[Finding]:
    """References nothing points to are dead weight: the agent only loads
    files that SKILL.md (or an already-loaded reference) names."""
    findings = []
    ref_files = _reference_files(skill)
    texts = {}
    for f in ref_files:
        if f.suffix.lower() in _REFERENCE_EXTS:
            try:
                texts[f] = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                texts[f] = ""
    for f in ref_files:
        haystack = skill.body + "".join(
            text for other, text in texts.items() if other != f)
        if f.name in haystack:
            continue
        rel = f.relative_to(skill.path).as_posix()
        findings.append(Finding(
            INFO, "REFERENCE_ORPHAN",
            f"{rel} is never pointed to from SKILL.md or another reference. "
            f"The agent will never load it; add a pointer ('When X, read "
            f"{rel}') or prune it"))
    return findings


DUPLICATE_PARA_MIN_CHARS = 120
_DUPLICATE_REPORT_CAP = 5


def _check_duplication(skill: Skill) -> List[Finding]:
    """The same paragraph in two places is two copies to keep in sync.
    Keep a single source of truth and point to it."""
    sources = [("SKILL.md", skill.body)]
    for f in _reference_files(skill):
        if f.suffix.lower() not in _REFERENCE_EXTS:
            continue
        try:
            sources.append((f.relative_to(skill.path).as_posix(),
                            f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue

    seen = {}  # normalized paragraph -> [locations]
    for location, text in sources:
        for para in re.split(r"\n\s*\n", text):
            normalized = " ".join(para.split())
            if len(normalized) < DUPLICATE_PARA_MIN_CHARS:
                continue
            seen.setdefault(normalized, []).append(location)

    findings = []
    duplicates = [(norm, locs) for norm, locs in seen.items() if len(locs) > 1]
    for normalized, locations in duplicates[:_DUPLICATE_REPORT_CAP]:
        findings.append(Finding(
            WARNING, "DUPLICATE_TEXT",
            f"the same paragraph appears {len(locations)}× "
            f"({', '.join(dict.fromkeys(locations))}). Keep one source of "
            f"truth and point to it: \"{normalized[:60]}…\""))
    if len(duplicates) > _DUPLICATE_REPORT_CAP:
        findings.append(Finding(
            WARNING, "DUPLICATE_TEXT",
            f"…and {len(duplicates) - _DUPLICATE_REPORT_CAP} more duplicated "
            f"paragraphs"))
    return findings


def _check_scripts(skill: Skill) -> List[Finding]:
    findings = []
    scripts_dir = skill.path / "scripts"
    if not scripts_dir.is_dir():
        return findings
    for script in sorted(scripts_dir.rglob("*")):
        if not script.is_file() or script.name == ".DS_Store":
            continue
        rel = script.relative_to(skill.path)
        if script.suffix in (".py", ".sh", ".js", ".rb", ""):
            try:
                first_line = script.read_text(encoding="utf-8",
                                              errors="replace").splitlines()[:1]
            except OSError:
                continue
            if not first_line or not first_line[0].startswith("#!"):
                findings.append(Finding(
                    INFO, "SCRIPT_NO_SHEBANG",
                    f"{rel} has no shebang; that's fine if SKILL.md says how "
                    f"to run it (e.g. 'python3 {rel}')"))
    return findings


def _runtime_scan_corpus(skill: Skill) -> str:
    """Everything an agent following this skill reads: SKILL.md body,
    flow.toml (directives print runnable commands), and references."""
    parts = [skill.body]
    flow_file = skill.path / "flow.toml"
    if flow_file.is_file():
        try:
            parts.append(flow_file.read_text(encoding="utf-8",
                                             errors="replace"))
        except OSError:
            pass
    for ref in _reference_files(skill):
        if ref.suffix.lower() in _REFERENCE_EXTS:
            try:
                parts.append(ref.read_text(encoding="utf-8",
                                           errors="replace"))
            except OSError:
                pass
    return "\n".join(parts)


def _check_runtime(skill: Skill, for_packaging: bool) -> List[Finding]:
    """The bundled runtime (scripts/steer.py) vs what the skill asks of it."""
    from . import __version__
    from .vendor import (COMPONENT_MODULES, RUNTIME_REL_PATH,
                         read_runtime_header, runtime_state)

    corpus = _runtime_scan_corpus(skill)
    components = "|".join(COMPONENT_MODULES)
    # A bundled-runtime invocation (`python3 scripts/steer.py store ...`)
    # vs the installed-CLI spelling of the same commands (`steer store ...`).
    runtime_call = re.compile(rf"scripts/steer\.py\s+({components})\b")
    installed_call = re.compile(rf"\bsteer\s+({components})\b")

    findings = []
    header = read_runtime_header(skill.path)

    if header is None:
        if "scripts/steer.py" in corpus:
            if (skill.path / RUNTIME_REL_PATH).is_file():
                findings.append(Finding(
                    WARNING, "RUNTIME_HEADER",
                    "scripts/steer.py has no parseable steer-runtime header; "
                    "steer can't verify or refresh it. Regenerate: "
                    "steer bundle --with <components>"))
            else:
                findings.append(Finding(
                    ERROR, "RUNTIME_MISSING",
                    "the skill invokes scripts/steer.py but has no bundled "
                    "runtime. Generate it: steer bundle --with "
                    "<components>"))
        return findings

    called = set(runtime_call.findall(corpus))
    missing = called - set(header.components)
    if missing:
        findings.append(Finding(
            ERROR if for_packaging else WARNING, "RUNTIME_COMPONENT",
            f"the skill invokes component(s) the bundled runtime doesn't "
            f"include: {', '.join(sorted(missing))} (bundled: "
            f"{', '.join(header.components)}). Rebundle: steer bundle "
            f"--with {','.join(header.components + sorted(missing))}"))

    state = runtime_state(skill.path, header=header)
    if state == "stale":
        findings.append(Finding(
            INFO, "RUNTIME_STALE",
            f"bundled runtime was written by steer {header.version} (this "
            f"is {__version__}); it still works. steer package refreshes "
            f"it, or run: steer bundle"))
    elif state == "edited":
        findings.append(Finding(
            ERROR if for_packaging else WARNING, "RUNTIME_EDITED",
            "scripts/steer.py differs from steer's output for its declared "
            "components; it is generated code and edits will be lost. "
            "Regenerate it (steer bundle) and put changes in your own "
            "scripts instead"))

    if installed_call.search(corpus):
        findings.append(Finding(
            INFO, "RUNTIME_SPELLING",
            "the skill calls the installed CLI (`steer <component> ...`) "
            "even though it bundles its runtime; prefer `python3 "
            "scripts/steer.py <component> ...` so the skill runs without "
            "steer installed"))
    return findings


LEARNINGS_LINE_BUDGET = 150


def _check_learnings(skill: Skill) -> List[Finding]:
    findings = []
    learnings = skill.path / "learnings.md"
    if not learnings.is_file():
        return findings
    try:
        line_count = len(learnings.read_text(encoding="utf-8").splitlines())
    except OSError:
        return findings
    if line_count > LEARNINGS_LINE_BUDGET:
        findings.append(Finding(
            WARNING, "LEARNINGS_LONG",
            f"learnings.md is {line_count} lines (guidance: "
            f"<{LEARNINGS_LINE_BUDGET}). Distill or archive old lessons; "
            f"stale lessons degrade the skill"))
    if ("learnings.md" not in skill.body
            and not re.search(r"steer(\.py)?\s+learn\b", skill.body)):
        findings.append(Finding(
            INFO, "LEARNINGS_UNREFERENCED",
            "learnings.md exists but SKILL.md never mentions it; the agent "
            "won't know to read it"))
    return findings


def _check_hygiene(skill: Skill, for_packaging: bool) -> List[Finding]:
    findings = []
    level = ERROR if for_packaging else WARNING
    for pattern in SECRET_FILE_PATTERNS:
        for hit in skill.path.rglob(pattern):
            if not hit.is_file():
                continue
            rel = hit.relative_to(skill.path)
            if any(part in (".git", "node_modules") for part in rel.parts):
                continue
            findings.append(Finding(
                level, "SECRET_FILE",
                f"{rel} looks like a credential file. Skill directories get "
                f"zipped and uploaded; keep secrets outside the skill "
                f"(use `steer secrets`)"))

    total = skill.total_size()
    if total >= SIZE_MAX_BYTES:
        findings.append(Finding(
            ERROR, "TOO_LARGE",
            f"skill is {total / 1024 / 1024:.1f}MB; the Claude API rejects "
            f"zips over 30MB"))
    elif total >= SIZE_WARN_BYTES:
        findings.append(Finding(
            WARNING, "LARGE",
            f"skill is {total / 1024 / 1024:.1f}MB; consider trimming assets"))
    return findings


def summarize(findings: List[Finding]) -> str:
    """One-line summary: '2 errors, 1 warning, 3 info'."""
    errors = sum(1 for f in findings if f.level == ERROR)
    warnings = sum(1 for f in findings if f.level == WARNING)
    infos = sum(1 for f in findings if f.level == INFO)
    if not findings:
        return "clean"
    return f"{errors} error(s), {warnings} warning(s), {infos} info"


def has_errors(findings: List[Finding]) -> bool:
    return any(f.level == ERROR for f in findings)
