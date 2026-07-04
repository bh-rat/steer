# Conversions: famous skills, rebuilt on steer

An experiment: take widely used open skills, rebuild each on steer
with `steer new` plus the components it hand-rolls, preserve the
original's content and voice, and measure what changes. Results with
numbers live in [COMPARISON.md](COMPARISON.md); each skill's NOTICE.md
records its origin, license, and the exact deltas.

| Directory | Origin | Components used |
|---|---|---|
| [`webapp-testing`](webapp-testing) | anthropics/skills | context, proc, learn |
| [`systematic-debugging`](systematic-debugging) | obra/superpowers | flow, learn |
| [`vercel-cli-with-tokens`](vercel-cli-with-tokens) | vercel-labs/agent-skills | secrets, store, context, learn |
| [`humanizer`](humanizer) | blader/humanizer | flow, store, learn |

The humanizer conversion was performed by the `converting-skills`
skill in [`skills/`](../../skills), driving its enforced triage, scaffold,
port, verify, compare flow; the conversion playbook distilled from all
four ports lives in that skill's `references/`.

Each is installable as-is:

```bash
steer validate examples/conversions/webapp-testing
steer install examples/conversions/webapp-testing
```

The comparison harness under [`compare/`](compare) is self-contained
and deterministic: five behavior checks plus a static metrics table,
runnable on any laptop against fresh clones of the originals.
