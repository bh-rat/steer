# Rebuilding famous skills on steer: what actually changes

Four famous open Agent Skills, rebuilt on steer with their content and
behavior preserved, then measured against the originals. Every number
below is reproducible from this directory; no LLM judging is involved.

| Original | Source (license) | What it exercises |
|---|---|---|
| `webapp-testing` | anthropics/skills (Apache-2.0) | managed processes, context recon |
| `systematic-debugging` | obra/superpowers (MIT) | flow enforcement, learning loop |
| `vercel-cli-with-tokens` | vercel-labs/agent-skills (MIT per README; repo ships no LICENSE file) | credentials, store, context |
| `humanizer` | blader/humanizer (MIT) | flow with output gates, store, context economy |

The originals are famous for a reason: all three pass `steer validate`
with zero errors. The differences live in runtime behavior, failure
modes, and context economy, which is exactly where published skill
benchmarks are thinnest (see "How this relates to published testing").

## The scoreboard

Five deterministic checks, run by `compare/behavior.py`:

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
   port is still bound. `steer proc stop` kills the process group:
   child dead, port free.
2. **A chatty server deadlocks it.** Server output goes to a pipe
   nobody reads; past the pipe buffer the server blocks mid-write
   before binding its port. Measured: a healthy server that logs 4096
   build lines is reported "failed to start" after the full 10.2s
   timeout. Under `steer proc` (log file, not pipe) it is ready in
   0.3s.
3. **Startup failures are undiagnosable.** stderr is piped and
   dropped. Measured: a server that dies printing
   "FATAL: DATABASE_URL is not set" produces a timeout error that
   never mentions the cause. `steer proc start` fails in 0.3s and the
   error carries the log tail including the cause.
4. **Dead processes are polled anyway.** The original waits the full
   timeout (6.1s measured) polling a port owned by a process that
   exited in the first millisecond; steer detects the exit immediately.

The rebuild deletes the script entirely (105 lines to 0) and gains
captured logs, readiness checks, stale-PID detection, and a lessons
loop. Cost, reported honestly: the SKILL.md body grew from ~894 to
~1133 estimated tokens (+27%), mostly the learning section.

## Case 2: systematic-debugging (superpowers)

The original's methodology is deliberately tuned prose (Iron Law, red
flags, rationalization table) and the rebuild keeps that voice
verbatim. What changes is enforcement. The original says "You MUST
complete each phase before proceeding"; nothing checks. The rebuild
gives each phase a verify condition on the artifact the prose already
demands ("write it down", "list every difference"): evidence,
comparison, hypothesis, and failing-test records under `out/debug/`.

Measured: `steer flow done fix` on a fresh workspace is refused with
exit 1 ("Step 'fix' is blocked"); the current step advances
investigate, analyze, hypothesize, failing-test in exact order as
artifacts appear; 5/5 steps complete only after all artifacts exist.
The agent that wants to skip to the fix now needs to fabricate
evidence files rather than merely ignore a sentence.

Also found by conversion: the original ships five files nothing
references (three pressure-test transcripts, a test scenario, the
creation log; 11.8KB), creation-time artifacts in the installed skill.
The rebuild drops them and moves the four real technique docs behind
`references/` pointers. Body: ~2430 to ~2245 tokens, while adding the
flow and learning sections.

## Case 3: vercel-cli-with-tokens (Vercel)

The original is 353 lines, of which the first quarter is a hand-rolled
credential cascade: check `VERCEL_TOKEN`, grep `.env`, recognize
`vca_` prefixes, export, and ask the user as a last resort. It even
warns (correctly) never to pass tokens as CLI flags. But its own
discovery step C is `grep -i 'vercel' .env`, which prints the token
value into the conversation transcript. Measured with a canary token:
the value reaches the output verbatim.

The rebuild collapses the cascade into `steer secrets`
(environment, OS keychain, and 0600 file resolved by one check),
detects `.env` variables by name only, moves values by shell
substitution, and persists via `steer secrets set` so discovery
happens once, not every session. Measured: the missing-token path
exits 1 with the exact command to give the user; the found path never
prints the value. The project/team binding becomes `steer store`
workspace state instead of per-session rediscovery.

Context economy: troubleshooting, domains, and Stripe plan sections
move behind `references/` pointers. Body: ~2525 to ~1936 estimated
tokens (-23%) with identical capability.

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
  pointers the every-trigger body drops to ~7207 tokens (-13%). The
  remaining overage is the patterns themselves, kept deliberately:
  that trim belongs to the original author, not a port (NOTICE.md).
- **The skill's own rule, machine-held.** The original's process ends
  "contains no em or en dashes" as prose. The rebuild's flow refuses
  to count the final stage complete while the artifact contains one.
  Measured: with an em dash in `out/humanize/final.md` the flow
  reports 2/3 complete; removing it flips the same command to 3/3.
- **Voice profiles persist.** The original re-analyzes the user's
  writing sample every session; the rebuild stores the analyzed
  profile per user (`steer store`) and reads it back next run.
- Frontmatter: the original's top-level `version:` is not a spec
  field (clients ignore it); it moved to `metadata.version`.

This conversion was driven end to end by the `converting-skills` skill
in `skills/`, through its enforced triage, scaffold, port, verify,
compare flow.

## Static comparison

From `compare/metrics.py` (tokens estimated at 4 chars/token, the
same estimate `steer validate` uses):

| | body tokens | shipped script lines | files nothing references | validate |
|---|---|---|---|---|
| webapp-testing original | 894 | 214 | 0 | 1 info |
| webapp-testing steer | 1133 | 108 | 0 | clean |
| systematic-debugging original | 2430 | 221 | 5 | 1 info |
| systematic-debugging steer | 2245 | 221 | 0 | clean |
| vercel-cli-with-tokens original | 2525 | 0 | 0 | clean |
| vercel-cli-with-tokens steer | 1936 | 0 | 0 | clean |
| humanizer original | 8329 | 0 | 1 | 3 warnings, 1 info |
| humanizer steer | 7207 | 0 | 0 | 2 warnings (deliberate, see NOTICE) |

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

The five checks here target exactly that uncovered part: the
credential is missing, the server is chatty or dead, the step is
skipped. They are deterministic, free to run, and require no eval
cluster. They do not measure end-task quality or trigger reliability;
for those, Anthropic's skill-creator eval loop and promptfoo's
skill-used assertions are the current options, and the honest prior
from the literature is that content-level gains are task-dependent.

## Reproduce

```bash
# originals (four shallow clones)
mkdir -p /tmp/skill-originals && cd /tmp/skill-originals
git clone --depth 1 https://github.com/anthropics/skills anthropic-skills
git clone --depth 1 https://github.com/obra/superpowers superpowers
git clone --depth 1 https://github.com/vercel-labs/agent-skills vercel-agent-skills
git clone --depth 1 https://github.com/blader/humanizer humanizer

# from this directory
python3 compare/behavior.py --originals /tmp/skill-originals
python3 compare/metrics.py  --originals /tmp/skill-originals
```

Requires `steer` on PATH (or `STEER_BIN=...`), Python 3.11+, no other
dependencies. Each rebuild's NOTICE.md records exactly what changed
from its original; LICENSE.txt carries the original license where the
source repository ships one.
