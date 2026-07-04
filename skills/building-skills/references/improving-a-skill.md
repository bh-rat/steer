# Improving an existing skill

The request is a review, a fix, or a tune-up: the skill already exists
and someone is unhappy with it. Work from evidence, not taste.

1. **Find it.** `steer list` shows installed skills with a validation
   status each; or the user points at a directory.
2. **Baseline.** Run `steer validate <dir>`. Fix errors first (spec
   violations, broken references, a missing bundled runtime), then
   warnings, then info. The finding-to-fix map is at the end of
   `writing-the-body.md` in this directory.
3. **Weigh the body.** Over budget means the trigger got expensive:
   push branch-only sections into references/ behind pointers. Check
   the description against what users actually say to invoke it; thin
   or trigger-less descriptions are the most common reason a skill
   never fires.
4. **Harvest the lessons.** If the skill has learn wired in, run
   `python3 <skill-dir>/scripts/steer.py learn review`: promote the
   keepers (`learn promote <id>`), archive the stale
   (`learn forget <id>`), both through the same runtime. A learnings.md
   past 150 lines gets distilled into the body or references, not
   appended to.
5. **Replace hand-rolls with components.** Grep the body for the
   tells: ALL-CAPS step enforcement (flow), probe-the-environment
   preambles (context), scratch files in /tmp or dot-dirs (store),
   paste-me-the-key prose (secrets), spawn-and-pray servers (proc).
   Each swap is `steer bundle --with ...` plus one copied section,
   guided by `choosing-components.md` in this directory.
6. **Re-verify.** `steer validate` clean, `steer install <dir> --force`
   where it was installed, then one real run in a fresh context. Read
   the trace, not just the output: did it load the references it
   needed, in the order you expected?
7. **Leave a record.** Keep the skill's name and voice; change what
   evidence supports. Capture what you changed and why against this
   skill's own runtime:
   `python3 <building-skills-dir>/scripts/steer.py learn note "<rule>"`.

The goal is a smaller, sharper skill. Ending with more lines than you
started is usually the wrong direction.
