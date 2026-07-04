# Skills that ship with steer

First-party skills, built with steer's own tooling and validated in CI.
Install them with the CLI they teach:

```bash
steer install skills/building-skills --user   # project scope: drop --user
```

## building-skills

The skill that builds skills. Once installed, "build me a skill for X"
walks the agent through steer's whole lifecycle behind an enforced
flow: design (trigger, components, structure, grounded in the user's
source material), scaffold with `steer new`, write, then two gates it
cannot talk its way past: no TODO left in the workspace, and
`steer validate` passing. It finishes by installing the new skill and
exercising it on a real task, and it gets better at the job over time;
build lessons accumulate through its learn component.

It was scaffolded the way it tells agents to work:

```bash
steer new building-skills --with learn \
  --steps design,scaffold,write,validate,exercise --refs \
  --description "..."
```

and it takes only the components it needs (flow and learn; no secrets,
no store, no proc), with a bundled runtime carrying exactly those two,
the same restraint it prescribes. The one extra requirement over a
normal steer-built skill: authoring drives `steer new`, `steer
validate`, and `steer install`, so the installed CLI has to be present
(the skill checks and says so).

## converting-skills

The conversion counterpart. Once installed, "port this skill to steer"
walks the agent through a gated conversion: triage (inventory, license
check, component map), scaffold with `steer new`, a faithful port that
keeps the original's voice and records every delta in a NOTICE.md, a
live `steer validate` gate, and a measured comparison against the
original. Its `references/` distill the playbook from the four real
conversions in [`examples/conversions`](../examples/conversions); the
humanizer rebuild there was produced by this skill end to end.

Like building-skills it takes only flow and learn, runs them from its
bundled runtime, and needs the installed CLI only for the authoring
commands it drives.

Relation to [`examples/`](../examples): examples show what steer
generates and how finished skills read; `skills/` is tooling you
install and use.
