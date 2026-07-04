"""
Learning: skills that improve from their own runs.

Skills are static; agents repeat the same mistakes run after run. The
memory systems that hold up in practice share one shape: automatic capture,
deterministic curation, gated application. Steer implements that loop for
skills:

- **Capture**: the agent records lessons as it works:
  ``steer learn note "Use the EU endpoint for EU accounts" --kind correction``
- **Apply**: at the start of a run the agent reads the bounded digest:
  ``steer learn show``
- **Curate**: deterministic, no LLM inside the framework (the agent IS
  the reflector): exact-duplicate notes bump a confirmation counter,
  ``confirm``/``dispute`` adjust scores, lessons disputed more than
  confirmed auto-archive, and a hard cap evicts the weakest.
- **Promote**: the human-gated path into the shipped skill:
  ``steer learn promote <id>`` appends to the skill's ``learnings.md``.

Where everything lives. Lessons stay OUTSIDE the skill directory (skill
dirs get zipped, uploaded, and upstream-updated; learned data must
survive reinstalls and must never ship by accident):

    ~/.steer/skills/<name>/
    ├── lessons.db       # source of truth (SQLite: lessons + runs)
    └── LEARNINGS.md     # auto-maintained readable mirror of lessons.db
    <skill-dir>/learnings.md   # promoted lessons only; ships with the skill

Auto-learning: ``steer learn reflect`` is a Claude Code Stop hook. It
deterministically scans the session transcript for correction/failure
signals and, once, blocks the stop with instructions telling the agent
to distill lessons before finishing. ``steer new --auto-learn`` wires it
into a skill's frontmatter ``hooks`` so capture no longer depends on the
agent remembering.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import skill_data_dir

KINDS = ("correction", "failure", "success", "preference", "workaround", "note")

ACTIVE = "active"
PINNED = "pinned"
ARCHIVED = "archived"
PROMOTED = "promoted"

MAX_LESSON_CHARS = 500       # lessons are atomic rules, not essays
MAX_ACTIVE_LESSONS = 200     # hard cap; weakest evicted past this
DEFAULT_SHOW_BUDGET = 2000   # chars in the `show` digest (~500 tokens)

LEARNINGS_FILE = "learnings.md"   # promoted lessons, inside the skill (ships)
MIRROR_FILE = "LEARNINGS.md"      # auto-maintained readable mirror, ~/.steer

# Obvious credential shapes. Lessons are plain text that may eventually be
# promoted into a shipped file. Refuse anything that smells like a secret.
_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|passwd|password|bearer)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}"),
    re.compile(r"\bxox[bpars]-[A-Za-z0-9-]+"),
]


class LessonRejected(Exception):
    """A lesson was refused (too long, or credential-shaped)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".").lower()


class Learnings:
    """The learning loop for one skill."""

    def __init__(self, skill: str, path: Optional[Path] = None):
        if not skill and path is None:
            raise ValueError("Learnings requires a skill name")
        self.skill = skill
        self.path = path or (skill_data_dir(skill, create=True) / "lessons.db")
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS lessons ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  text TEXT NOT NULL,"
                "  normalized TEXT NOT NULL,"
                "  kind TEXT NOT NULL,"
                "  context TEXT,"
                "  evidence TEXT,"
                "  skill_version TEXT,"
                "  workspace TEXT,"
                "  status TEXT NOT NULL DEFAULT 'active',"
                "  confirmations INTEGER NOT NULL DEFAULT 1,"
                "  contradictions INTEGER NOT NULL DEFAULT 0,"
                "  created_at TEXT NOT NULL,"
                "  last_seen_at TEXT NOT NULL"
                ")"
            )
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS runs ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  status TEXT NOT NULL,"
                "  note TEXT,"
                "  workspace TEXT,"
                "  skill_version TEXT,"
                "  created_at TEXT NOT NULL"
                ")"
            )
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Learnings":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- capture --------------------------------------------------------

    def note(self, text: str, kind: str = "note", context: Optional[str] = None,
             evidence: Optional[str] = None, skill_version: Optional[str] = None,
             workspace: Optional[str] = None) -> Dict[str, Any]:
        """Record a lesson. Exact duplicates confirm instead of duplicating.

        Returns {"id", "action"} where action is "added" or "confirmed".
        """
        text = text.strip()
        if not text:
            raise LessonRejected("Empty lesson.")
        if len(text) > MAX_LESSON_CHARS:
            raise LessonRejected(
                f"Lesson is {len(text)} chars (max {MAX_LESSON_CHARS}). "
                f"Keep lessons atomic: one rule per note; split this one."
            )
        for pattern in _SECRET_PATTERNS:
            if any(pattern.search(part) for part in (text, context, evidence)
                   if part):
                raise LessonRejected(
                    "This looks like it contains a credential. Lessons are "
                    "plain text and can be promoted into shipped files. "
                    "Store secrets with `steer secrets` instead."
                )
        if kind not in KINDS:
            raise LessonRejected(
                f"Unknown kind {kind!r} (use one of: {', '.join(KINDS)})"
            )

        normalized = _normalize(text)
        existing = self.conn.execute(
            "SELECT id FROM lessons WHERE normalized = ? "
            "AND status IN ('active', 'pinned')",
            (normalized,),
        ).fetchone()
        if existing:
            self.confirm(existing["id"])
            return {"id": existing["id"], "action": "confirmed"}

        cur = self.conn.execute(
            "INSERT INTO lessons (text, normalized, kind, context, evidence,"
            " skill_version, workspace, status, created_at, last_seen_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (text, normalized, kind, context, evidence, skill_version,
             workspace, _now(), _now()),
        )
        self.conn.commit()
        self._evict_past_cap()
        self.sync_mirror()
        return {"id": int(cur.lastrowid), "action": "added"}

    def record_run(self, status: str, note: Optional[str] = None,
                   skill_version: Optional[str] = None,
                   workspace: Optional[str] = None) -> int:
        """Record a run outcome ("ok" or "failed") for stats."""
        if status not in ("ok", "failed"):
            raise ValueError("Run status must be 'ok' or 'failed'")
        cur = self.conn.execute(
            "INSERT INTO runs (status, note, workspace, skill_version,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            (status, note, workspace, skill_version, _now()),
        )
        self.conn.commit()
        self.sync_mirror()
        return int(cur.lastrowid)

    # -- curation (deterministic: no LLM in the framework) ---------------

    def _get(self, lesson_id: int) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM lessons WHERE id = ?", (lesson_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No lesson with id {lesson_id}")
        return row

    def confirm(self, lesson_id: int) -> Dict[str, Any]:
        """This lesson helped. Strengthen it."""
        self._get(lesson_id)
        self.conn.execute(
            "UPDATE lessons SET confirmations = confirmations + 1,"
            " last_seen_at = ?,"
            " status = CASE WHEN status = 'archived' THEN 'active'"
            "               ELSE status END"
            " WHERE id = ?",
            (_now(), lesson_id),
        )
        self.conn.commit()
        self.sync_mirror()
        return self.get(lesson_id)

    def dispute(self, lesson_id: int) -> Dict[str, Any]:
        """This lesson was wrong or no longer applies. Weaken it.

        A lesson disputed more than confirmed auto-archives: bounded blast
        radius for bad lessons, reversible by a later confirm.
        """
        self._get(lesson_id)
        self.conn.execute(
            "UPDATE lessons SET contradictions = contradictions + 1,"
            " last_seen_at = ? WHERE id = ?",
            (_now(), lesson_id),
        )
        self.conn.execute(
            "UPDATE lessons SET status = 'archived'"
            " WHERE id = ? AND contradictions > confirmations"
            " AND status IN ('active', 'pinned')",
            (lesson_id,),
        )
        self.conn.commit()
        self.sync_mirror()
        return self.get(lesson_id)

    def pin(self, lesson_id: int) -> None:
        """Pin a lesson: always shown first, never auto-evicted."""
        self._get(lesson_id)
        self.conn.execute(
            "UPDATE lessons SET status = 'pinned', last_seen_at = ?"
            " WHERE id = ?", (_now(), lesson_id),
        )
        self.conn.commit()
        self.sync_mirror()

    def forget(self, lesson_id: int) -> None:
        """Archive a lesson (soft delete; review --all still shows it)."""
        self._get(lesson_id)
        self.conn.execute(
            "UPDATE lessons SET status = 'archived' WHERE id = ?",
            (lesson_id,),
        )
        self.conn.commit()
        self.sync_mirror()

    def _evict_past_cap(self) -> None:
        rows = self.conn.execute(
            "SELECT id FROM lessons WHERE status = 'active'"
            " ORDER BY (confirmations - contradictions) DESC, last_seen_at DESC"
        ).fetchall()
        for row in rows[MAX_ACTIVE_LESSONS:]:
            self.conn.execute(
                "UPDATE lessons SET status = 'archived' WHERE id = ?",
                (row["id"],),
            )
        if len(rows) > MAX_ACTIVE_LESSONS:
            self.conn.commit()

    # -- reading ----------------------------------------------------------

    def get(self, lesson_id: int) -> Dict[str, Any]:
        return dict(self._get(lesson_id))

    def lessons(self, statuses: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Lessons ranked: pinned first, then score, then recency."""
        wanted = statuses or [PINNED, ACTIVE]
        marks = ",".join("?" for _ in wanted)
        rows = self.conn.execute(
            f"SELECT * FROM lessons WHERE status IN ({marks})"
            " ORDER BY CASE status WHEN 'pinned' THEN 0 ELSE 1 END,"
            " (confirmations - contradictions) DESC, last_seen_at DESC",
            wanted,
        ).fetchall()
        return [dict(r) for r in rows]

    def digest(self, budget: int = DEFAULT_SHOW_BUDGET,
               current_version: Optional[str] = None) -> str:
        """The bounded markdown the agent reads at the start of a run."""
        ranked = self.lessons()
        if not ranked:
            return ("(no lessons recorded for this skill yet; capture them "
                    "as you work: steer learn note \"...\")")

        lines = [f"## Lessons from previous runs ({self.skill})"]
        shown = 0
        used = len(lines[0])
        for lesson in ranked:
            marker = "★ " if lesson["status"] == PINNED else ""
            stale = ""
            if (current_version and lesson["skill_version"]
                    and lesson["skill_version"] != current_version):
                stale = f" [from v{lesson['skill_version']}]"
            entry = f"- [{lesson['id']}] {marker}{lesson['text']}{stale}"
            if lesson["context"]:
                entry += f" (when: {lesson['context']})"
            if used + len(entry) > budget:
                break
            lines.append(entry)
            used += len(entry)
            shown += 1
        remaining = len(ranked) - shown
        if remaining > 0:
            lines.append(f"- …and {remaining} more: steer learn review")
        lines.append(
            "(helped? steer learn confirm <id> · wrong? steer learn dispute <id>)"
        )
        return "\n".join(lines)

    def stats(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for row in self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM lessons GROUP BY status"
        ):
            by_status[row["status"]] = row["n"]
        runs = {"total": 0, "ok": 0, "failed": 0}
        for row in self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM runs GROUP BY status"
        ):
            runs[row["status"]] = row["n"]
            runs["total"] += row["n"]
        last_run = self.conn.execute(
            "SELECT created_at FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "skill": self.skill,
            "lessons": by_status,
            "runs": runs,
            "success_rate": (runs["ok"] / runs["total"]) if runs["total"] else None,
            "last_run": last_run["created_at"] if last_run else None,
        }

    # -- the readable mirror (the "specific place" lessons live) ----------

    def mirror_path(self) -> Path:
        return self.path.parent / MIRROR_FILE

    def sync_mirror(self) -> Path:
        """Regenerate the human/agent-readable LEARNINGS.md next to the DB.

        The DB is the source of truth; the mirror is rewritten after every
        mutation so it can simply be read (or grepped) without the CLI.
        """
        stats = self.stats()
        runs = stats["runs"]
        rate = (f"{stats['success_rate'] * 100:.0f}% ok"
                if stats["success_rate"] is not None else "no runs yet")
        counts = stats["lessons"]
        lines = [
            f"# Learnings: {self.skill}",
            "",
            "<!-- auto-generated by steer learn; source of truth is "
            "lessons.db in this directory. Edit via `steer learn` commands, "
            "not by hand. -->",
            "",
            f"Updated: {_now()} · runs: {runs['total']} ({rate}) · "
            + " · ".join(f"{counts.get(s, 0)} {s}"
                         for s in (PINNED, ACTIVE, PROMOTED, ARCHIVED)),
        ]
        sections = [
            ("Pinned", [PINNED], None),
            ("Active", [ACTIVE], None),
            ("Promoted (shipped in the skill's learnings.md)", [PROMOTED], 10),
            ("Recently archived", [ARCHIVED], 10),
        ]
        for title, statuses, limit in sections:
            entries = self.lessons(statuses)
            if not entries:
                continue
            lines += ["", f"## {title}", ""]
            for lesson in entries[:limit] if limit else entries:
                score = lesson["confirmations"] - lesson["contradictions"]
                line = (f"- [{lesson['id']}] {lesson['text']} "
                        f"({lesson['kind']}, {score:+d}")
                if lesson["context"]:
                    line += f", when: {lesson['context']}"
                line += f", last: {lesson['last_seen_at'][:10]})"
                if lesson["evidence"]:
                    line += f"; evidence: {lesson['evidence']}"
                lines.append(line)
            if limit and len(entries) > limit:
                lines.append(f"- …and {len(entries) - limit} more "
                             f"(steer learn review --all)")
        self.mirror_path().write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self.mirror_path()

    # -- promotion (the human-gated path into the shipped skill) ----------

    def promote(self, lesson_id: int, skill_dir) -> Path:
        """Append a lesson to the skill's learnings.md and mark it promoted.

        This is the author action that turns a learned-locally lesson into
        shipped skill content. The file is plain markdown with provenance
        comments, so diffs are reviewable and upstream merges are sane.
        """
        lesson = self._get(lesson_id)
        target_dir = Path(skill_dir).expanduser()
        if not (target_dir / "SKILL.md").is_file():
            raise FileNotFoundError(
                f"{target_dir} is not a skill directory (no SKILL.md)"
            )
        learnings_path = target_dir / LEARNINGS_FILE
        if not learnings_path.exists():
            learnings_path.write_text(
                "# Learnings\n\n"
                "Lessons promoted from real runs (managed with `steer learn`).\n"
                "Read this before relying on the main instructions.\n\n",
                encoding="utf-8",
            )
        date = _now().split("T")[0]
        entry = f"- {lesson['text']}"
        if lesson["context"]:
            entry += f" (when: {lesson['context']})"
        entry += f" <!-- steer:lesson {lesson['id']} {date} -->\n"
        with open(learnings_path, "a", encoding="utf-8") as f:
            f.write(entry)
        self.conn.execute(
            "UPDATE lessons SET status = 'promoted', last_seen_at = ?"
            " WHERE id = ?", (_now(), lesson_id),
        )
        self.conn.commit()
        self.sync_mirror()
        return learnings_path


# -- auto-learning: the Stop-hook reflection engine -----------------------
#
# `steer learn reflect` runs as a (Claude Code) Stop hook. Steer stays
# LLM-free: it only DETECTS that something worth learning happened
# (user corrections, failed tool calls) and, once per session, blocks the
# stop with instructions telling the agent (the actual reflector) to
# distill lessons and record the run outcome before finishing.

# User-message shapes that signal a correction. Deterministic and
# deliberately conservative: false negatives are cheap (the instruction-
# driven loop still applies), false positives nag.
_CORRECTION_PATTERNS = [
    re.compile(r"^\s*(no|nope|wrong|incorrect|not that|stop)\b[\s,.!]", re.I),
    re.compile(r"\b(that'?s (wrong|not right|not what)|you should have"
               r"|i meant|i didn'?t ask|don'?t do that|undo that"
               r"|use .{1,40} instead|not .{1,40}, use)\b", re.I),
]

_CAPTURE_MARKERS = ("steer learn note", "steer learn run")


def _iter_transcript_text(line_obj: Any):
    """Yield (role, text) pairs from one parsed transcript line.

    Claude Code transcripts are JSONL but the exact line shape varies
    (top-level role/content, or nested under "message"). Walk both.
    """
    if not isinstance(line_obj, dict):
        return
    message = line_obj.get("message") if isinstance(line_obj.get("message"), dict) else line_obj
    role = message.get("role") or line_obj.get("type") or ""
    content = message.get("content")
    if isinstance(content, str):
        yield role, content
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    yield role, text


def scan_transcript(path) -> Dict[str, Any]:
    """Deterministically scan a session transcript for learning signals.

    Returns {"corrections": int, "failures": int, "captured": bool,
    "readable": bool}. `captured` means the agent already ran
    `steer learn note`/`run` this session.
    """
    result = {"corrections": 0, "failures": 0, "captured": False,
              "readable": False}
    try:
        raw = Path(path).expanduser().read_text(encoding="utf-8",
                                                errors="replace")
    except OSError:
        return result
    result["readable"] = True

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Cheap signals that don't need full parsing
        if '"is_error": true' in line or '"is_error":true' in line:
            result["failures"] += 1
        if any(marker in line for marker in _CAPTURE_MARKERS):
            result["captured"] = True
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        for role, text in _iter_transcript_text(obj):
            if role != "user":
                continue
            if any(p.search(text) for p in _CORRECTION_PATTERNS):
                result["corrections"] += 1
    return result


def reflect(hook_input: Dict[str, Any], skill: str,
            min_signals: int = 1) -> Optional[Dict[str, Any]]:
    """Decide whether to block a stop and ask the agent to distill lessons.

    Returns the Stop-hook decision object ({"decision": "block", ...}) or
    None to allow the stop. Never blocks twice (honors stop_hook_active),
    never blocks when the agent already captured this session.
    """
    if hook_input.get("stop_hook_active"):
        return None
    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        return None
    signals = scan_transcript(transcript_path)
    if not signals["readable"] or signals["captured"]:
        return None
    total = signals["corrections"] + signals["failures"]
    if total < min_signals:
        return None

    observed = []
    if signals["corrections"]:
        observed.append(f"{signals['corrections']} user correction(s)")
    if signals["failures"]:
        observed.append(f"{signals['failures']} failed tool call(s)")
    reason = (
        f"steer learn (skill '{skill}'): this session had "
        f"{' and '.join(observed)}, and no lessons were recorded. "
        f"Before finishing:\n"
        f"1. For each durable, reusable lesson run: steer learn note "
        f"\"<one imperative rule>\" --kind correction --skill {skill} "
        f"(skip one-off trivia; never include secrets)\n"
        f"2. Record the outcome: steer learn run ok --skill {skill} "
        f"(or 'failed')\n"
        f"Then finish. If nothing is durable, just record the run outcome."
    )
    return {
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": reason,
        },
    }
