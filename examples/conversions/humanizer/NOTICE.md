# Notice

This skill is a rebuild of `humanizer` by Siqi Chen (blader/humanizer,
MIT License; full text in LICENSE.txt), restructured on the steer
framework as a conversion study. The 33 patterns, personality
guidance, detection guidance, and voice are the original author's
content, kept verbatim.

Changes from the original:

- The draft, audit, final process became an enforced flow
  (`flow.toml`): each stage completes only when its artifact exists
  under `out/humanize/`, and the final stage is additionally
  machine-checked against the skill's own rule 14: it cannot complete
  while the final rewrite contains an em or en dash.
- Voice calibration moved behind `references/voice-calibration.md`
  (loaded only when the user provides a sample), and the analyzed
  profile now persists per user via `steer store`, so repeat users
  skip re-analysis.
- The full worked example moved to `references/full-example.md`.
- A lesson capture loop (`steer learn`) was added.
- Top-level `version: 2.8.2` (not a spec field) moved to
  `metadata.version`.
- Deliberately NOT fixed: the body keeps all 33 patterns with their
  examples inline and still exceeds the 500-line / 5k-token guidance
  (575 lines, ~7.2k estimated tokens, down from 602 / ~8.3k). The
  patterns are tuned teaching content and splitting them risks
  changing behavior; that trim belongs to the original author, not a
  port.
