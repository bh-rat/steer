# Choosing components

Every component you wire in becomes instructions the agent carries on
every run of the new skill. The default is none; each one has to earn
its place by replacing something the skill would otherwise hand-roll in
prose or fragile bash. Across the skills we analyzed, most needed one or
two, not all six.

| The skill needs | Component | Wire it in with |
|---|---|---|
| API keys or tokens | secrets | `--secrets KEY[,KEY]` |
| Data that survives between runs | store | `--with store` |
| A look at the environment first | context | `--with context` |
| Steps that must happen in order | flow | `--steps id,id,...` |
| A server or watcher while it works | proc | `--with proc` |
| To improve from its own runs | learn | `--with learn` |

Choosing any component also writes the skill's bundled runtime, a
generated `scripts/steer.py` holding exactly those components (stdlib
only, Python 3.11 or newer), and the generated sections invoke it with
`python3`, so whoever runs the skill needs Python, not steer. `--scripts`
(example script with the result envelope) and `--refs` (references/ and
assets/ directories) shape the directory rather than the runtime. All
flags combine into one `steer new` call, and `--secrets` and `--steps`
take real names, so the generated instructions come out concrete instead
of generic.

## secrets

Reach for it when the skill calls anything authenticated. The generated
section makes the agent check, the human set, and the value never appear
in chat or inside the skill directory (`steer package` refuses
credential-looking files). Skip it when nothing is authenticated, and
never accept a key pasted into SKILL.md, a script, or an .env inside the
skill.

## store

Reach for it when a run should know about previous runs: totals to trend
against, cursors, seen-before lists. `--scope workspace` keeps project
data with the project; the default user scope follows the user across
projects. Skip it for single-shot transforms; a value the skill can
recompute cheaply does not need persisting.

## context

Reach for it when behavior branches on the environment: platform, git
state, project type, which tools exist here. One snapshot command
replaces the probe-and-guess preamble. Skip it when the skill would read
the snapshot and change nothing.

## flow

Reach for it when the process has phases that must land in order and
"done" is checkable: files exist, commands pass. Steps with verify
conditions complete only against reality; judgment steps stay mandate
steps the agent marks after doing them. Skip it when the body's numbered
list is honestly enough, meaning nothing breaks if the agent reorders or
compresses steps.

## proc

Reach for it when the skill starts servers or watchers it must also
stop: readiness by port or log line, logs captured, no zombies. Skip it
for processes the user starts and owns.

## learn

Reach for it when the skill will run repeatedly and corrections should
stick: capture as they happen, digest at run start, promote keepers into
the shipped skill. On Claude Code, `--auto-learn` adds a Stop hook so
capture stops depending on the agent remembering; the hook is the one
piece that runs the installed CLI, and other clients ignore it
(`steer validate` flags it as a portability warning). Skip learn for
one-off or purely mechanical skills.

## Runtime truth

A finished skill runs its components through its own bundle: no steer
install, no version skew, and commands that resolve their skill from the
file's location rather than flags. The bundle is generated code with a
header naming its steer version and components; regenerate it with
`steer bundle` (validation catches stale, edited, or missing bundles,
and packaging refreshes stale ones). The installed CLI stays an
author-time tool.
