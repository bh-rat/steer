# Examples: skills built with steer

Both skills here were scaffolded by `steer new` and finished the way the
scaffold itself directs: replace every TODO, define the real flow steps,
`steer validate` until clean. The structure (every section header, the
enforcement prose, the credential handoff, the learning loop, the script
contract) is steer's generated output; the author supplied the one
description paragraph, the real steps, the gotchas, and the domain scripts.

## repo-health: every component in one skill

```bash
steer new repo-health \
  --description "Generates a repository health report: commit activity, code inventory, TODO debt, test presence. Use when the user asks for a repo health check, codebase overview, or tech-debt snapshot." \
  --with secrets,store,context,flow,proc,learn --scripts \
  --secrets REPO_HEALTH_WEBHOOK --steps collect,report,review
```

Produces `out/health/REPORT.md` for any repository, with trends against
the previous run. The scaffold also wrote `scripts/steer.py`, the
skill's bundled runtime: a generated, self-contained copy of exactly
these six components, which is what SKILL.md invokes, so agents run
this skill with plain `python3`, no steer install. What each component
does here:

| Component | Role in this skill |
|---|---|
| `context` | step 0: platform, project type, git state before doing anything |
| `flow` | `collect → report → review`; the agent cannot claim done early |
| `store` | previous run's totals (workspace scope) → the report's Trend arrows |
| `secrets` | optional webhook for `scripts/share.py`; never inside the skill dir |
| `proc` | optional report preview server, started/stopped managed |
| `learn` | lessons captured during runs, digest read at the start of the next |

The three domain scripts follow the contract of steer's generated
`scripts/example.py`: single JSON envelope on stdout, diagnostics on
stderr. They import steer's library helpers (`Store`, `Secrets`,
`print_envelope`) from the bundled runtime sitting next to them, with a
graceful fallback if it's missing.

Try it on any repo:

```bash
steer install examples/repo-health        # → .claude/skills/repo-health
```

then ask your agent for "a health check of this repo".

## commit-message: minimal and user-invoked

```bash
steer new commit-message --user-invoked --refs \
  --description "Writes a conventional commit message from the staged diff, one logical change at a time."
```

The other end of the spectrum: no scripts and no flow, just five steps and
one reference. `--user-invoked` sets `disable-model-invocation: true` (you
call it; it never auto-triggers), and the type-picking cheatsheet lives
behind a context pointer in `references/`, loaded only when needed.

## conversions/: famous skills, rebuilt and measured

The two skills above were written from scratch to show what steer
generates. [`conversions/`](conversions) is the other direction:
widely used third-party skills rebuilt on steer with their content
preserved, each under its original license (see the NOTICE.md in each
folder), with a deterministic comparison harness and measured results
in [`conversions/COMPARISON.md`](conversions/COMPARISON.md).

## Verified end-to-end

`repo-health` has been executed by an agent in a sandboxed workspace,
following the SKILL.md exactly as written: the flow refused a premature
`done review` and only completed against reality; a second run produced
real trend arrows from the store; the preview server started
port-ready and stopped clean; the missing webhook produced the
agent-asks-human handoff and the secret landed in `$STEER_HOME` (0600),
never in the skill; the lesson captured mid-run surfaced in the next
`learn show`.

Check them yourself:

```bash
steer validate examples/repo-health       # clean
steer validate examples/commit-message    # one info: the deliberate trigger choice
```
