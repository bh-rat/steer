---
name: repo-health
description: "Generates a repository health report: commit activity, code inventory, TODO debt, test presence. Use when the user asks for a repo health check, codebase overview, or tech-debt snapshot."
metadata:
  version: 0.1.0
---

# repo-health
Produce a one-page health report for the repository in the current
workspace: recent commit activity, what the codebase is made of, how much
marked debt (TODO/FIXME) it carries, and whether tests exist. The result
the user gets is `out/health/REPORT.md`, with trends against the previous
run.

## Before you start

1. **Ground yourself.** Run `steer context` and read the snapshot before doing anything else; it tells you the platform, project type, git state, and which tools exist here.
2. **Apply past lessons.** Run `steer learn show --skill repo-health` and follow what it says; those lessons came from real previous runs.
3. **Check credentials**, only when the user wants the summary posted to
   their webhook (`scripts/share.py`). Run `steer secrets check
   REPO_HEALTH_WEBHOOK --skill repo-health`. If it is missing, ask the user
   to run `steer secrets set REPO_HEALTH_WEBHOOK --skill repo-health`
   (never ask them to paste the value into the chat), then re-check.

## Process

This skill has an enforced flow: steps verify themselves against
reality, and you cannot skip ahead.

1. Announce: "Working through the repo-health flow."
2. Run `steer flow status` (in the workspace) to see progress and the
   current step.
3. Do what the directive says. Steps with a verify condition complete
   automatically once reality matches; for mandate steps, mark completion
   with `steer flow done <step-id>`.
4. Run `steer flow next` and repeat until it reports all steps complete.

Do NOT claim the work is done while `steer flow status` shows incomplete
steps. The flow is defined in `flow.toml`.

## Memory

This skill persists data between runs with `steer store` (per-skill
SQLite). `scripts/report.py` records this run's totals at workspace scope
to power the report's Trend section; if the user asks "compared to what?":

    steer store get last_totals --skill repo-health --scope workspace

Use `--scope workspace` for state that belongs to this project rather
than the user.

## Background processes

Start helpers through steer so nothing leaks or zombies. If the user wants
to browse the report:

    steer proc start health-preview --ready-port 8642 -- python3 -m http.server 8642 --directory out/health
    steer proc status health-preview
    steer proc stop health-preview      # always stop what you started

## Learning

This skill improves with use. As you work:

- The moment the user corrects you, or something fails and then works a
  different way, capture it:
  `steer learn note "<one imperative rule>" --kind correction --skill repo-health`
  Lessons are atomic rules ("Use X not Y when Z"), never secrets.
- When a lesson from `steer learn show --skill repo-health` helped, run
  `steer learn confirm <id> --skill repo-health`; when one was wrong,
  `steer learn dispute <id> --skill repo-health`.
- Before finishing, record the outcome:
  `steer learn run ok --skill repo-health` (or `failed` with `--note`).

If a `learnings.md` exists in this skill, read it too; those are
promoted lessons that shipped with the skill.

## Output

Scripts print a single JSON result envelope to stdout
(`{"status", "summary", "data", "artifacts"}`); read `status` instead of
parsing prose. Diagnostics go to stderr.

## Gotchas

- Not a git repository → `collect` still works; the Activity section says
  so instead of failing.
- The scripts skip `.git`, virtualenvs, `node_modules`, build output, and
  `out/` itself; binary and >1MB files are excluded from line counts.
- The report is a snapshot, not a judgment: present findings, let the
  user decide what matters.
