# Rebuilding sample skills on steer: what actually changes

Four sample open Agent Skills, rebuilt on steer with their content and
behavior preserved, then measured against the originals. Every number
below comes from deterministic checks (no LLM judging); the method for
each is described at the end.

| Original | Source (license) | What it exercises |
|---|---|---|
| `webapp-testing` | anthropics/skills (Apache-2.0) | managed processes, context recon |
| `systematic-debugging` | obra/superpowers (MIT) | flow enforcement, learning loop |
| `vercel-cli-with-tokens` | vercel-labs/agent-skills (MIT per README; repo ships no LICENSE file) | credentials, store, context |
| `humanizer` | blader/humanizer (MIT) | flow with output gates, store, context economy |

The originals are well built: all four pass `steer validate`
with zero errors. The differences live in runtime behavior, failure
modes, and context economy, which is exactly where published skill
benchmarks are thinnest (see "How this relates to published testing").

Every rebuild carries its own generated runtime (`scripts/steer.py`,
written by `steer bundle`) holding exactly its components, so the
skills and every check below run with plain `python3`, no steer
install.

## The scoreboard

Six deterministic checks, run through the rebuilds' own bundled
runtimes with plain `python3`:

| Check | Original | Steer rebuild |
|---|---|---|
| Server child after cleanup (T1) | exits 0, child ALIVE, port still bound | child dead, port free |
| Verbose server startup (T2) | false "failed to start" after 10.2s | ready in 0.3s |
| Server dies at startup (T3) | 6.1s wait, cause absent from output | fails in 0.3s, cause in output |
| Premature "done" on debugging flow (T4) | prose only; nothing refuses | refused with exit 1; steps unlock in phase order; 5/5 only after artifacts exist |
| Token discovery (T5) | documented command prints the token value into the transcript | names-only check, exit 1 handoff with the exact fix command, value never printed |
| Final rewrite containing an em dash (T6) | rule 14 is prose; nothing checks the output | flow refuses to count the final step done until the artifact is dash-free |

## Case 1: webapp-testing (Anthropic)

The original bundles `scripts/with_server.py`, 105 lines that spawn
servers, poll ports, and clean up. That is the same lifecycle every
server-touching skill rewrites, and this copy has four measurable
defects:

1. **Cleanup leaks the actual server.** The script starts commands
   through a shell and later terminates only what it spawned; for
   wrapper commands (`npm run dev` spawning node, here reproduced with
   a Python wrapper) the real server survives. Measured: the original
   exits 0 reporting success while the server child is alive and the
   port is still bound. The rebuild's `proc stop` kills the process
   group: child dead, port free.
2. **A chatty server deadlocks it.** Server output goes to a pipe
   nobody reads; past the pipe buffer the server blocks mid-write
   before binding its port. Measured: a healthy server that logs 4096
   build lines is reported "failed to start" after the full 10.2s
   timeout. Under the rebuild's `proc` (log file, not pipe) it is
   ready in 0.3s.
3. **Startup failures are undiagnosable.** stderr is piped and
   dropped. Measured: a server that dies printing
   "FATAL: DATABASE_URL is not set" produces a timeout error that
   never mentions the cause. The rebuild's `proc start` fails in 0.3s
   and the error carries the log tail including the cause.
4. **Dead processes are polled anyway.** The original waits the full
   timeout (6.1s measured) polling a port owned by a process that
   exited in the first millisecond; steer detects the exit immediately.

The rebuild deletes the script entirely (105 hand-written lifecycle
lines to 0; the lifecycle now lives in the generated bundled runtime,
executed, never read into context) and gains captured logs, readiness
checks, stale-PID detection, and a lessons loop. Cost, reported
honestly: the SKILL.md body grew from ~894 to ~1250 estimated tokens
(+40%), the learning section and the bundled-runtime preamble.

## Case 2: systematic-debugging (superpowers)

The original's methodology is deliberately tuned prose (Iron Law, red
flags, rationalization table) and the rebuild keeps that voice
verbatim. What changes is enforcement. The original says "You MUST
complete each phase before proceeding"; nothing checks. The rebuild
gives each phase a verify condition on the artifact the prose already
demands ("write it down", "list every difference"): evidence,
comparison, hypothesis, and failing-test records under `out/debug/`.

Measured: `flow done fix` on a fresh workspace is refused with exit 1
("Step 'fix' is blocked"); the current step advances investigate,
analyze, hypothesize, failing-test in exact order as artifacts appear;
5/5 steps complete only after all artifacts exist. The agent that
wants to skip to the fix now needs to fabricate evidence files rather
than merely ignore a sentence.

Also found by conversion: the original ships five files nothing
references (three pressure-test transcripts, a test scenario, the
creation log; 11.8KB), creation-time artifacts in the installed skill.
The rebuild drops them and moves the four real technique docs behind
`references/` pointers. Body: ~2430 to ~2332 tokens, while adding the
flow, learning, and runtime sections.

## Case 3: vercel-cli-with-tokens (Vercel)

The original is 353 lines, of which the first quarter is a hand-rolled
credential cascade: check `VERCEL_TOKEN`, grep `.env`, recognize
`vca_` prefixes, export, and ask the user as a last resort. It even
warns (correctly) never to pass tokens as CLI flags. But its own
discovery step C is `grep -i 'vercel' .env`, which prints the token
value into the conversation transcript. Measured with a canary token:
the value reaches the output verbatim.

The rebuild collapses the cascade into the secrets component
(environment, OS keychain, and 0600 file resolved by one check),
detects `.env` variables by name only, moves values by shell
substitution, and persists via the hidden-prompt `secrets set` so
discovery happens once, not every session. Measured: the missing-token
path exits 1 with the exact command to give the user; the found path
never prints the value. The project/team binding becomes store
workspace state instead of per-session rediscovery.

Context economy: troubleshooting, domains, and Stripe plan sections
move behind `references/` pointers. Body: ~2525 to ~1988 estimated
tokens (-21%) with identical capability.

## Case 4: humanizer (blader)

The viral single-file skill: 622 lines, pure prose, no machinery at
all, which makes it the honest boundary test. Its 33 patterns are
tuned teaching content; the rebuild keeps them byte-identical and does
not pretend steer improves them.

What conversion still found:

- **Context cost.** The original loads ~8329 estimated tokens into
  context on every trigger, 66% over the 5k guidance
  (`steer validate` flags it). The worked example and the voice
  calibration branch are load-on-demand material; behind `references/`
  pointers the every-trigger body drops to ~7294 tokens (-12%). The
  remaining overage is the patterns themselves, kept deliberately:
  that trim belongs to the original author, not a port (NOTICE.md).
- **The skill's own rule, machine-held.** The original's process ends
  "contains no em or en dashes" as prose. The rebuild's flow refuses
  to count the final stage complete while the artifact contains one.
  Measured: with an em dash in `out/humanize/final.md` the flow
  reports 2/3 complete; removing it flips the same command to 3/3.
- **Voice profiles persist.** The original re-analyzes the user's
  writing sample every session; the rebuild stores the analyzed
  profile per user (the store component) and reads it back next run.
- Frontmatter: the original's top-level `version:` is not a spec
  field (clients ignore it); it moved to `metadata.version`.

This conversion was driven end to end by the `converting-skills` skill
in `skills/`, through its enforced triage, scaffold, port, verify,
compare flow.

## Static comparison

Tokens are estimated at 4 chars/token, the same estimate
`steer validate` uses. Hand-written lines are code the skill's author
maintains; the generated runtime is written by `steer bundle`,
executed, never read into context, and regenerated rather than
edited:

| | body tokens | hand-written script lines | generated runtime lines | files nothing references | validate |
|---|---|---|---|---|---|
| webapp-testing original | 894 | 214 | 0 | 0 | 1 info |
| webapp-testing steer | 1250 | 108 | 2308 | 0 | clean |
| systematic-debugging original | 2430 | 221 | 0 | 5 | 1 info |
| systematic-debugging steer | 2332 | 221 | 2533 | 0 | clean |
| vercel-cli-with-tokens original | 2525 | 0 | 0 | 0 | clean |
| vercel-cli-with-tokens steer | 1988 | 0 | 2587 | 0 | clean |
| humanizer original | 8329 | 0 | 0 | 1 | 3 warnings, 1 info |
| humanizer steer | 7294 | 0 | 2823 | 0 | 2 warnings (deliberate, see NOTICE) |

The webapp-testing script delta that matters: 105 of the original's
214 lines are the server-lifecycle helper, deleted outright; the
other 109 are the three Playwright pattern examples, byte-identical
in both versions (the original ships them under `examples/`, the
rebuild under `references/` behind explicit pointers).

## How this relates to published testing

As of mid-2026 there is no established public benchmark for skills.
SkillsBench (arXiv 2602.12670) reports +16.6pp average from curated
skills across 18 configurations; SWE-Skills-Bench (arXiv 2603.15401)
finds 39 of 49 skills add nothing on a high baseline; a UCSB and MIT
study (arXiv 2604.04323) shows gains degrading as conditions get
realistic. None of them measure what happens when a precondition
breaks. A June 2026 paper (arXiv 2606.20659) measures that gap:
existing benchmark runs exercise roughly 40 to 44 percent of skills'
stated behavior constraints.

The six checks here target exactly that uncovered part: the
credential is missing, the server is chatty or dead, the step is
skipped. They are deterministic, free to run, and require no eval
cluster. They do not measure end-task quality or trigger reliability;
for those, Anthropic's skill-creator eval loop and promptfoo's
skill-used assertions are the current options, and the honest prior
from the literature is that content-level gains are task-dependent.

## Method

The originals were measured from fresh shallow clones of
anthropics/skills, obra/superpowers, vercel-labs/agent-skills, and
blader/humanizer; the rebuilds from this directory. Each behavior
check is a few lines of orchestration:

- **T1**: a wrapper script that spawns the real HTTP server as a
  child (the shape of `npm run dev`). Original side: run
  `with_server.py` around a trivial automation command, then probe the
  child pid and the port after it exits. Rebuild side: `proc start`
  with `--ready-port`, then `proc stop`, same probes.
- **T2**: a server that writes 4096 build lines to stdout before
  binding its port, run under a 10 second timeout on both sides.
- **T3**: a server that prints "FATAL: DATABASE_URL is not set" to
  stderr and exits 1; check whether that cause appears in each side's
  output and how long the failure takes.
- **T4**: drive the debugging flow in an empty workspace: `flow done
  fix` first (expect refusal), then create the four `out/debug/`
  artifacts in order, reading `flow status --json` between each.
- **T5**: `secrets check VERCEL_TOKEN` against an isolated
  `STEER_HOME`, first empty and then with the variable exported; then
  a `.env` containing a canary token, running the original's
  documented grep next to a names-only grep and searching both
  outputs for the canary value.
- **T6**: with draft and tells artifacts present, write an em dash
  into `out/humanize/final.md` and read `flow status`; remove it and
  read again.

Static numbers: SKILL.md body tokens at 4 chars/token; script lines
split into hand-written vs generated on the steer-runtime header;
dead files found by scanning every text file for mentions of each
sibling; validation via `steer validate --json`.

Each rebuild's NOTICE.md records exactly what changed from its
original; LICENSE.txt carries the original license where the source
repository ships one.
