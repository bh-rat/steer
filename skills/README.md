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

Relation to [`examples/`](../examples): examples show what steer
generates and how finished skills read; `skills/` is tooling you
install and use.
