# Writing the body

The scaffold gives you the structure; this is how to fill it so the
skill works when a fresh agent, without this conversation, has to run
it.

## The description first

It is the only thing the model sees before deciding to use the skill,
so it does two jobs in up to 1024 characters: what the skill does, then
when to use it, in the words a user would actually say.

- Lead with the verb ("Reviews a pull request and posts findings"),
  then the trigger ("Use when the user asks for a PR review, code
  review, or pre-merge check").
- Use the user's vocabulary, not the implementation's: they say
  "invoice", not "billing-object PDF render".
- Be a little pushy; agents under-trigger far more than they
  over-trigger. Name the nearby phrasings the skill should catch.
- Write in third person; the description lands in a system prompt.
- For `--user-invoked` skills the description is a label in a human's
  skill list; drop the trigger phrasing and keep it short.

While writing it, collect five requests that should trigger the skill
and five near-misses that should not. The near-misses tell you which
words to leave out now, and both lists get used at the exercise step.

## Body steps

- Numbered steps, each one action with an observable result.
- Say "Run:" when the agent must execute and "See:" when it must read;
  a bare filename invites the wrong one.
- Write for a capable agent: skip what any competent model does by
  default. A line that does not change behavior is a no-op that costs
  context on every run. For emphasis, explain why once instead of
  shouting MUST.
- Prefer one precise, load-bearing term over a paragraph of don'ts:
  idempotent, dry run, atomic, append-only. You will see the term
  echoed in the agent's reasoning when it lands.
- Every-run material stays in the body. Branch-only material goes to
  references/ behind a pointer that says when to load it ("When the
  form has signatures, first read references/signatures.md"). Budgets:
  body under 500 lines, about 5k tokens.
- Keep the scaffold's command spellings. Generated sections invoke the
  skill's bundled runtime with `python3`; rewriting them to call an
  installed steer reintroduces the dependency the bundle removed
  (validation flags that spelling).

## flow.toml for the new skill

Give a flow to a process that must hold its order, and a verify
condition to every step whose "done" is observable:

- `file_exists`, `dir_exists`, `glob`: an artifact proves the step.
- `command` (exit 0, 60s timeout): a check proves it, e.g. tests pass.
- `env`: a variable is set.
- No condition makes a mandate step: the agent marks it done, and
  marking is refused until its `requires` are complete. Use mandate
  steps for judgment (review, confirm) and nothing else.
- Use `{skill_dir}` and `{workspace}` in directives so printed commands
  run verbatim wherever the skill is installed.
- For destructive or batch operations, add a plan step that writes a
  plan file (verify: it exists) and make the execute step require it.
- Three to six steps, each named by what it produces ("collect",
  "report", "review"), not by how it feels.

## Scripts

Scripts are executed, not read; code never enters context, which makes
them the cheapest place for bulk. The contract the scaffolded example
follows:

- Non-interactive, fails fast, `--help` that actually documents.
- One JSON envelope on stdout: a status from `ok`, `error`, `blocked`,
  `needs_input`, `partial`, plus summary, data, artifacts. Diagnostics
  go to stderr. The generated example prints it with the standard
  library, so it runs anywhere Python does.
- The agent reads `status`, never parses prose; exit codes stay
  distinct.
- Sibling scripts that want the component library import it from the
  bundle next to them (`from steer import Store`), not from an
  installed steer.

Bundle a script when every run would rewrite the same code; leave
judgment in prose. Fragile operations get scripts on purpose: narrower
freedom where mistakes cost the most.

## Secrets in prose

The scaffolded Check credentials step already spells the exact
commands: the agent runs the check, the human runs the set (the value
is prompted, hidden, and stored outside the skill), and the agent
re-checks. Keep that shape, never ask for the value in chat, and in
library code pass `hint=` so the error says where to find the
credential.

## Prune, then validate

- Delete every instruction that does not change behavior; when unsure,
  cut it and compare a run.
- One source of truth per fact; the second copy is the one that goes
  stale.
- The write gate greps for the marker "TODO" followed by a colon
  (the generated `scripts/steer.py` is exempt); in the rare case the
  skill's own content needs that literal, phrase it another way.
- What `steer validate` findings mean:

| Finding | Fix |
|---|---|
| DESC_THIN, DESC_NO_TRIGGER | rewrite the description: what + when |
| BODY_LONG, BODY_TOKENS | move branch-only detail to references/ |
| LINK_BROKEN, RESOURCE_MISSING | create the file or fix the path |
| REFERENCE_ORPHAN | add a "when X read Y" pointer, or delete it |
| DUPLICATE_TEXT | keep one copy where it belongs, point to it |
| RUNTIME_MISSING, RUNTIME_COMPONENT, RUNTIME_STALE, RUNTIME_EDITED | regenerate the bundle: `steer bundle --with <components>` |
| RUNTIME_SPELLING | use the bundled `python3` spelling the scaffold wrote |
| PORTABILITY | a Claude-Code-only field; keep it only on purpose |
| SECRET_FILE | move the credential out of the skill directory |
| NAME_ and DESC_ errors | the spec's hard rules; fix exactly as told |
