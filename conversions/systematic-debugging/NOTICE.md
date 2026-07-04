# Notice

This skill is a rebuild of `systematic-debugging` from obra/superpowers
(MIT License, Copyright Jesse Vincent; full text in LICENSE.txt),
restructured on the steer framework as a conversion study. The
methodology, Red Flags list, rationalization table, and human partner
language are the original author's tuned content, kept deliberately.

Changes from the original:

- The four phases became an enforced flow (`flow.toml`). "You MUST
  complete each phase before proceeding" is now machine-checked: each
  investigation phase completes only when its artifact exists under
  `out/debug/` (evidence, comparison, hypothesis, failing test record),
  and the fix step stays locked until then. The artifacts make explicit
  what the original already demanded in prose ("Write it down", "List
  every difference", "MUST have before fixing").
- The Quick Reference phase table is dropped; `steer flow status` shows
  live phase state instead.
- A lesson capture loop (`steer learn`) was added; disproven hypotheses
  and caught rationalizations become lessons for the next run.
- Supporting documents moved to `references/` and the bisection script
  to `scripts/` (the spec's conventional directories), contents
  unchanged except two path mentions of `find-polluter.sh`.
- Not carried over: `test-pressure-1/2/3.md`, `test-academic.md`, and
  `CREATION-LOG.md`, five creation-time artifacts that shipped inside
  the original skill directory but are never referenced by its SKILL.md.
- `license: MIT` and `metadata.version` added to the frontmatter.
