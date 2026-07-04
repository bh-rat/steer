# Measuring a rebuild against its original

Write `out/conversion/comparison.md` from this checklist. Everything
here is deterministic and free; no LLM judging. Report both directions
honestly; a rebuild that costs more context in exchange for machinery
should say so.

## Static (always)

1. **Validation both sides.** `steer validate <dir> --json` on the
   original and the rebuild. Expect famous originals to be clean or
   near-clean; the rebuild must be clean. Count errors, warnings,
   info.
2. **Body context cost both sides.** Token estimate of the SKILL.md
   body (chars/4 matches the validator). The body enters context on
   every trigger. Note what moved behind `references/` and its size;
   that cost became load-on-demand.
3. **Dead weight.** Files in the original's directory that nothing
   references (creation logs, test artifacts). They ship and are never
   loaded; list what the rebuild dropped.
4. **Description as trigger.** Both descriptions: presence of "use
   when" phrasing, and length (client skill listings truncate long
   entries; past the listing budget a skill can silently never fire).

## Failure modes (the axis nothing public measures)

Enumerate the skill's preconditions from its own body: a credential is
set, a server is up, a tool is installed, steps happen in order. For
each, break the precondition deliberately and observe both versions:

- missing credential: is the failure a clear ask-the-user handoff
  with the exact fix command, or a stack trace, or silence?
- dead or slow server: does startup failure carry the cause? does
  cleanup actually reclaim the port, or does a child process survive?
- skipped step: does anything refuse, or does prose merely disapprove?
- secret canary: put a fake token in a `.env`; run the skill's own
  discovery commands; grep every output for the canary value. A value
  that reaches the transcript is a leak.

One command per probe, exit codes and captured output as evidence.

## What not to claim

- Do not claim the original fails validation when it does not.
- Do not claim end-task quality improved; that needs task evals with
  trials, and published results say content-level gains are
  task-dependent. Claim what you measured: failure behavior,
  enforcement, secret hygiene, context economy.
