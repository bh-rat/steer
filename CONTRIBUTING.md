# Contributing to steer

Thanks for helping build the framework for Agent Skills.

## Ground rules

- **Zero runtime dependencies.** Steer is Python stdlib only (`sqlite3`,
  `tomllib`, `zipfile`, …). PRs that add a runtime dependency will be asked
  to find a stdlib way. Dev/CI tooling (pytest, ruff) is fine; it never
  ships.
- **Python ≥ 3.11**, macOS and Linux are the supported platforms today.
- **Agent-first UX.** Error messages tell the agent the exact next command
  to run. Every command that prints for humans also takes `--json`.
- **Spec first.** Scaffolds and validation target the
  [open Agent Skills spec](https://agentskills.io/specification);
  client-specific extensions (e.g. Claude Code hooks) are opt-in and flagged
  by `steer validate` as portability warnings.

## Dev setup

```bash
git clone https://github.com/bh-rat/steer && cd steer
uv venv && uv pip install -e . pytest
.venv/bin/python -m pytest tests/ -q
```

(Plain `python3 -m venv .venv && .venv/bin/pip install -e . pytest` works
too; there is nothing uv-specific here.)

## Before you open a PR

1. `python -m pytest tests/ -q`: all green, and new behavior has tests.
   Tests are stdlib `unittest`-style via pytest, hermetic (temp dirs, no
   network, no real `~/.steer`).
2. `uvx ruff check steer tests`: clean.
3. If you touched the CLI surface or on-disk formats, update the docs
   (`docs/`) and `CHANGELOG.md` in the same PR.

## Good first contributions

- New `steer context` detectors (project types, host agents); see
  `steer/context.py`.
- New `steer flow` verify conditions; see `steer/flow.py`.
- Validation checks with real-world evidence (link to the skill that
  motivated them).

For anything bigger, open an issue first so we can agree on the shape.
