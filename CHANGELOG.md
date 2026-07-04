# Changelog

All notable changes to steer are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/) (pre-1.0: minor bumps may break).

## 0.1.1: skills carry their own runtime

### Added

- Bundled runtime: `steer new` writes `scripts/steer.py` into every
  skill that uses components: a generated, self-contained copy of
  exactly the chosen components (Python ≥ 3.11, stdlib only). SKILL.md
  invokes it as `python3 scripts/steer.py <component> ...`, so agents
  run the skill without steer installed; sibling scripts get the library
  the same way (`from steer import Store`).
- `steer bundle [--with a,b,c]` writes or refreshes a skill's bundled
  runtime; without `--with` it re-reads the bundle's own header.
- The bundle resolves the skill it ships in from its own location:
  no `--skill` flags, no cwd guessing, and agent-facing hints (secrets
  remediation, learn digest, flow directives) spell commands the way
  the bundle is invoked.
- Validation understands bundles: `RUNTIME_MISSING`,
  `RUNTIME_COMPONENT`, `RUNTIME_EDITED`, `RUNTIME_STALE`, and
  `RUNTIME_SPELLING` findings. `steer package` refreshes a stale bundle
  before zipping and refuses an edited one.

### Changed

- Generated SKILL.md templates and the repo-health example use the
  bundled spelling throughout. The installed CLI keeps working exactly
  as before (runtime commands now live in `steer/runtime_cli.py`,
  shared by both entry points).
- The scaffolded example script no longer imports steer; it prints its
  result envelope with the standard library.

## 0.1.0: initial public release

Published on PyPI as `steer-ai` (the name `steer` was already taken);
the command and the import are `steer` either way.

### Highlights beyond the components

- `steer new` takes component inputs at scaffold time: `--secrets
  KEY[,KEY...]` wires named credentials into the generated instructions,
  `--steps id[,id...]` generates a linear chain of named flow steps, and
  `--user-invoked` scaffolds a human-triggered skill
  (`disable-model-invocation: true`) with validation adapting its trigger
  checks.
- `flow.toml` strings expand `{skill_dir}` and `{workspace}`, so printed
  directives run verbatim from the workspace even when the skill is
  installed under `.claude/skills/`.
- `steer validate` prunes as well as checks: `DUPLICATE_TEXT` (the same
  paragraph in two places) and `REFERENCE_ORPHAN` (reference files nothing
  points to).
- Two complete example skills in `examples/`, scaffolded by steer and
  verified end-to-end by an agent in a sandbox.

Steer is the framework for building [Agent Skills](https://agentskills.io):
authoring tools around the whole lifecycle, plus the runtime components the
SKILL.md format deliberately leaves out. Zero dependencies: Python stdlib
only, Python ≥ 3.11.

### Author-time CLI

- `steer new`: scaffold a spec-valid skill; `--with
  secrets,store,context,flow,proc,learn` wires components into the generated
  SKILL.md, `--scripts` adds an example script with the result envelope,
  `--auto-learn` wires a Claude Code Stop hook for automatic lesson capture.
- `steer validate`: the open spec's hard rules (name/description/XML/size),
  progressive-disclosure budgets, broken references, portability warnings for
  Claude-Code-only frontmatter, thin-trigger descriptions, and secret hygiene.
- `steer package`: validated, API-ready zip; refuses credential-looking
  files.
- `steer install` / `steer list`: copy into / enumerate `.claude/skills`
  and `.agents/skills`, project and user scope.

### Runtime components (CLI and Python library)

- `steer secrets`: per-skill credentials, resolved env var → OS keychain (macOS
  `security` / Linux `secret-tool`) → `0600` file under `~/.steer/`. Never
  inside the skill directory.
- `steer store`: per-skill SQLite with KV + JSON-document tables + raw SQL,
  user or workspace scope.
- `steer context`: one-shot situational snapshot, covering platform, host
  agent, git state, project type, tools on PATH.
- `steer flow`: declarative steps in `flow.toml` with verify conditions
  (`file_exists`, `dir_exists`, `glob`, `command`, `env`); mandate steps
  gated on prerequisites.
- `steer proc`: managed background processes with port/log-pattern readiness,
  PID bookkeeping, TERM→KILL stop of the whole process group.
- `steer learn`: capture → curate → promote loop so skills improve from
  their own runs; deterministic curation, human-gated promotion,
  `steer learn reflect` transcript scanning for auto-capture.
- `steer.output`: one JSON result envelope for every script.
