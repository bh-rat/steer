# steer

**The framework for building Agent Skills.**

[![CI](https://github.com/bh-rat/steer/actions/workflows/ci.yml/badge.svg)](https://github.com/bh-rat/steer/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A5%203.11-3776AB)
![Zero dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)

[Agent Skills](https://agentskills.io) (a `SKILL.md` plus scripts) are the
open standard for packaging agent capabilities, supported by Claude Code,
Codex, Copilot, Cursor, Gemini CLI, and ~40 other clients. The format is
deliberately tiny, which means it ships no batteries: the spec says nothing
about credentials, persistence, context gathering, step enforcement, or
managed processes. Every serious skill hand-rolls some of these.

Steer provides them as components, plus the authoring tools to scaffold,
validate, package, and install skills. Zero dependencies; Python stdlib
only, and skills carry their runtime with them: `steer new` writes it into
the skill as `scripts/steer.py`, so running a steer-built skill needs
Python, not steer.

```
┌─ author-time ──────────────────────┐  ┌─ runtime (bundled into the skill) ─┐
│ steer new        scaffold a skill  │  │ steer secrets   credentials        │
│ steer bundle     vendored runtime  │  │ steer store     per-skill SQLite   │
│ steer validate   spec + hygiene    │  │ steer context   situational recon  │
│ steer package    API-ready zip     │  │ steer flow      enforced steps     │
│ steer install    into skill dirs   │  │ steer proc      managed processes  │
│ steer list       what's installed  │  │ steer learn     skills that learn  │
└────────────────────────────────────┘  └────────────────────────────────────┘
```

## Why

Steer's components are reverse-engineered from what good skills already
hand-roll in prose and fragile bash (enforced steps, situational recon,
persistent state, credentials, process lifecycles), turned into machinery
you get with one flag.

## Install

```bash
uv tool install steer-ai        # installs the `steer` command
# or: pip install steer-ai
# latest from main: uv tool install git+https://github.com/bh-rat/steer
steer --version
```

Requires Python ≥ 3.11. No runtime dependencies.

## Quickstart

```bash
steer new pr-review \
  --description "Reviews a pull request and posts findings. Use when the user asks for a PR review, code review, or pre-merge check." \
  --with secrets,context,flow,learn --secrets GITHUB_TOKEN --scripts
```

This scaffolds a spec-valid skill:

```
pr-review/
├── SKILL.md       # frontmatter + body with the components wired in
├── flow.toml      # declarative steps with verify conditions
└── scripts/
    ├── steer.py   # bundled runtime: exactly the chosen components
    └── example.py # non-interactive, JSON result envelope on stdout
```

The generated `SKILL.md` already tells the agent how to behave, through
the skill's own bundled runtime:

> 1. **Ground yourself.** Run `python3 scripts/steer.py context` and read
>    the snapshot.
> 2. **Apply past lessons.** Run `python3 scripts/steer.py learn show`;
>    those lessons came from real previous runs.
> 3. **Check credentials.** Run `python3 scripts/steer.py secrets check
>    GITHUB_TOKEN`. If one is missing, ask the user to run the
>    `secrets set` command it prints (never ask them to paste the value
>    into the chat).
> 4. **Follow the flow.** `python3 scripts/steer.py flow status` → do the
>    step → steps verify themselves against reality; you cannot skip ahead.

For a skill only the human should trigger, `steer new --user-invoked`
sets `disable-model-invocation: true` and validation adapts.

Then:

```bash
steer validate pr-review     # spec rules, broken refs, secret hygiene
steer install pr-review      # → .claude/skills/ (project scope)
steer package pr-review      # → validated zip for the Claude API / claude.ai
```

## Examples

Two complete skills built this way live in [`examples/`](examples/):
[`repo-health`](examples/repo-health) exercises all six components in
one skill (enforced flow, trend memory, credential handoff, managed
preview server, lesson capture), and
[`commit-message`](examples/commit-message) is the minimal user-invoked
counterpoint. Their READMEs show exactly which lines steer generated and
which the author filled in.

## The skill that builds skills

The authoring workflow above also ships as a skill of its own:
[`skills/building-skills`](skills/building-skills). Installed, it turns
"build me a skill" into the full lifecycle: it designs the trigger and
components with you, scaffolds with `steer new`, and works behind an
enforced flow that refuses to finish while TODOs remain, `steer
validate` fails, or the new skill has never survived a real run. Build
lessons accumulate across uses via `steer learn`.

```bash
steer install skills/building-skills --user
```

## The components

### `steer secrets`: credentials that never live in the skill

Skill directories get zipped and uploaded; credentials must live outside
them. Resolution order: env var → OS keychain (macOS `security` /
Linux `secret-tool`) → `0600` file under `~/.steer/`.

```bash
python3 scripts/steer.py secrets check GITHUB_TOKEN    # agent checks (bundled runtime)
steer secrets set GITHUB_TOKEN --skill pr-review       # human sets (hidden prompt)
```

```python
from steer import Secrets
key = Secrets("pr-review").require("GITHUB_TOKEN",
                                   hint="github.com/settings/tokens")
# missing -> MissingSecretError whose message tells the agent
# exactly what command to ask the human to run
```

### `steer store`: per-skill SQLite

```bash
steer store put last_run '"2026-06-11"' --skill pr-review
steer store insert runs '{"pr": 142, "findings": 3}' --skill pr-review
steer store find runs --where pr=142 --skill pr-review
```

KV + JSON-document tables + raw SQL. Two scopes: `user`
(`~/.steer/skills/<name>/store.db`) and `workspace`
(`<project>/.steer/<name>/store.db`).

### `steer context`: situational recon in one command

```bash
steer context                # markdown for the agent to read
steer context --json --only git,project,tools
```

One command reports the platform, host agent (Claude Code, Codex, Cursor,
and others), git state, project type (from lockfiles and manifests), tools
on PATH, and a small allowlist of env flags. It never dumps the environment.

### `steer flow`: steps the agent cannot skip

Define the process in `flow.toml`; steps with a `verify` condition complete
only when reality matches, mandate steps are marked explicitly, and marking
is gated on prerequisites:

```toml
[[steps]]
id = "configure"
directive = "Create out/config.json with the data sources"
[steps.verify]
file_exists = "out/config.json"

[[steps]]
id = "review"
directive = "Read the config and confirm the mappings look right"
requires = ["configure"]
```

```bash
steer flow status        # progress bar + current directive
steer flow next          # what to do now
steer flow done review   # mark a mandate step (refused if prereqs incomplete)
```

Verify conditions: `file_exists`, `dir_exists`, `glob`, `command` (exit 0),
`env`. Python API: `steer.Flow` / `steer.Step` for full programmatic control.

### `steer proc`: background processes that don't zombie

```bash
steer proc start web --ready-port 5173 -- npm run dev
steer proc status web
steer proc logs web
steer proc stop web      # TERM → wait → KILL, whole process group
```

It checks readiness by port or log pattern, keeps PID bookkeeping under
`<workspace>/.steer/proc/`, guards against recycled PIDs, and captures logs.

### `steer learn`: skills that improve from their own runs

Tooling exists to improve a skill before it ships, and agents carry runtime
memory; nothing connects the two, so a skill learns nothing from its own
runs. `steer learn` is that connection, a capture → curate → promote loop:
the agent records lessons the moment they happen, reads a bounded digest at
the start of every run, and the author promotes the keepers into the shipped
skill.

```bash
steer learn note "Skip vendored and generated files in the diff" --kind correction
steer learn show          # ranked digest the SKILL.md tells the agent to read
steer learn confirm 3     # helped → stronger;  dispute → weaker, auto-archives
steer learn promote 3     # human-gated: append to the skill's learnings.md
steer learn run ok && steer learn stats
```

Curation is deterministic (no LLM inside the framework; the agent is the
reflector): duplicates confirm instead of duplicating, disputed-more-than-
confirmed auto-archives, a hard cap evicts the weakest, credential-shaped
notes are refused.

The structure is fixed and inspectable: `~/.steer/skills/<name>/lessons.db`
(source of truth) plus an auto-maintained readable `LEARNINGS.md` mirror,
both outside the skill dir, so lessons survive reinstalls and never ship by
accident. Promoted lessons land in the skill's `learnings.md`, which does
ship.

**Auto-learning:** `steer new my-skill --auto-learn` wires a Claude Code
skill-scoped Stop hook running `steer learn reflect`. When the agent tries
to finish, it deterministically scans the session transcript for corrections
and failed tool calls, and (once) blocks the stop with exact capture
instructions. Capture no longer depends on the agent remembering to do it.

### Result envelope: one output shape for every script

```python
from steer.output import print_envelope
print_envelope("ok", "Report generated",
               data={"rows": 120}, artifacts=["out/report.pdf"])
```

```json
{
  "status": "ok",
  "summary": "Report generated",
  "data": {"rows": 120},
  "artifacts": ["out/report.pdf"]
}
```

## Validation

`steer validate` checks the open spec's hard rules (name format/length and
directory match, description 1-1024 chars, no XML), progressive-disclosure
budgets (<500-line body), broken file references, portability (Claude-Code-
only frontmatter), thin trigger descriptions, duplicated paragraphs across
SKILL.md and references (keep one source of truth), orphaned `references/`
files nothing points to, bundled-runtime integrity (a missing, stale, or
hand-edited `scripts/steer.py`), and secret hygiene: credential-looking
files inside a skill are warnings normally and hard errors at packaging
time. `steer package` refuses to ship them, and refreshes a stale bundle
before zipping.

## Library use

Everything the CLI does is importable (`from steer import Skill, Flow,
Secrets, Store, validate_skill, discover`) for building your own skill
tooling on top.

## What steer is not

Not a registry or installer ecosystem (use `npx skills`, Tessl, or plugin
marketplaces; steer sits upstream of them), not an eval harness (yet), and
not useful at runtime for pure-knowledge skills (a style guide needs no
database, though steer still helps author and validate it).

## Roadmap

Skill-to-skill dependencies / shared libraries, `steer test`
(trigger-regression + cross-runtime checks), signing/provenance, TypeScript
SDK, PyPI release.

## Docs & contributing

Full documentation lives in [`docs/`](docs/), a Fumadocs site whose content
is under [`docs/content/docs/`](docs/content/docs/) (introduction,
quickstart, a page per component, and the authoring guide, including the
checklist for writing skill bodies: trigger, structure, steering, pruning).
Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Security
reports go to [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
