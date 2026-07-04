# Mapping hand-rolled machinery to components

What to look for in the original, and what replaces it. Take only the
components the skill's shape demands; forcing one in is worse than
leaving it out.

| You find in the original | Component | The conversion move |
|---|---|---|
| Phase rules in capital letters, iron laws, red-flag lists, "you MUST complete X before Y", checkbox tracking | `flow` | Steps in flow.toml with `requires` chains. Give each gate a verify condition on the artifact the prose already demands; see below. |
| "Unpack, fix, repack, re-verify" loops; "never trust generation" | `flow` | A verify step whose `command` condition runs the checker; the step completes only when the check passes. |
| A bundled server/process helper script (spawn, poll a port, PID file, terminate on exit) | `proc` | Delete the script. `steer proc start <name> --ready-port N -- <cmd>` in SKILL.md, plus `status`, `logs`, `stop`. Multiple servers become multiple named procs with `--cwd`. |
| "Step 0: figure out the environment" preambles; tool checks; git state checks; platform shims | `context` | One line: `steer context --tools <binaries the skill needs>`. Delete the preamble. |
| Credential discovery cascades (check env, grep .env, ask the user); tokens in command flags | `secrets` | `steer secrets check NAME --skill <name>` first, export by substitution via `steer secrets get`, persist with `steer secrets set`. Never print values; detect .env variables by NAME only. |
| Scratch JSON files, dot-files, hand-typed state schemas, "compared to last run" | `store` | `steer store put/get` (workspace scope for per-project state, user scope for preferences and profiles). |
| Per-user calibration, style profiles, accumulated corrections | `store` + `learn` | Profiles in the store; corrections captured as lessons the moment they happen. |
| Scripts printing ad-hoc JSON or prose to stdout | envelope | `steer.output.print_envelope` with the ImportError fallback so scripts run without steer installed. |
| A directory of material only some runs need, or a body past ~500 lines | `references/` | Move behind one-line pointers: "When doing X, first read references/x.md." |

## Turning prose gates into verify conditions

The original usually tells you what the artifact is; it just never
checks it. "Write the hypothesis down" becomes
`file_exists = "out/<skill>/hypothesis.md"`. "List every difference"
becomes a comparison file. "The tests must pass" becomes
`command = "..."`. When a step is genuinely judgment (a review, a
conversation), leave it a mandate step; gating on prerequisites is
still real enforcement.

## Component selection by skill shape

- Linear process skill: flow, plus learn.
- Toolkit skill (many entry points, no fixed order): no flow; context
  and whichever of proc/secrets/store its operations touch.
- Knowledge skill (style guides, rule sets): usually no runtime
  components; steer's value is authoring hygiene, references
  structure, and validation. Say so rather than wiring components in.
- Anything that talks to an API: secrets, even if the original never
  mentions credentials.
- Anything that says "last time" or "profile": store.
- learn fits almost every skill and costs one section.
