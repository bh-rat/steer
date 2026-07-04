# Notice

This skill is a rebuild of `webapp-testing` from the anthropics/skills
repository (Apache License 2.0; full text in LICENSE.txt), restructured
on the steer framework as a conversion study.

Changes from the original:

- The bundled `scripts/with_server.py` (105 lines of server lifecycle
  code) is removed. Server management goes through `steer proc`, which
  adds process group termination, captured logs, readiness checks with
  diagnostics, and stale PID detection.
- `examples/` moved to `references/` (the spec's conventional directory
  for load-on-demand material), contents unchanged, each behind an
  explicit pointer in SKILL.md.
- Environment recon (`steer context`) and a lesson capture loop
  (`steer learn`) added.
- Trigger phrasing ("Use when ...") appended to the description;
  `metadata.version` added.
