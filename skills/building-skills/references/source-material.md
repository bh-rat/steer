# Source material

Skills fail most often by being written from general knowledge:
plausible steps nobody has run. Ground the design in material that
already exists, and prefer the material's evidence over your instincts.

## From a document (API reference, runbook, style guide, README)

- Read the whole thing before deciding the skill's shape; the parts
  that matter are rarely the parts that come first.
- Sort what you find into three piles: procedure (the verbs; they
  become body steps or flow steps), lookup material (tables, enums,
  field lists; they go to references/ or into a script), and invariants
  (limits, auth quirks, ordering rules; they become Gotchas).
- Distill, never paste. A copied page drifts from its source and spends
  the body budget; keep a link plus the sentences the agent actually
  needs, and note the doc version or date next to anything likely to
  drift.
- Treat the doc as claims, not truth. Run the commands, hit the
  endpoint, check the defaults, and encode what actually happened. Two
  of its examples, verified, beat ten of them raw.
- An API doc usually implies: scripts call the API, `--secrets` names
  the credential, and the doc's example calls become the script's first
  test.

## From this conversation (or a workflow the user repeats)

The transcript is the best source there is: it shows what worked, not
what should have worked. Mine it for:

- The exact commands that succeeded, flags included.
- Every correction the user made; each becomes a Gotcha or a lesson, in
  their words.
- The failure-then-fix pairs; encode the fix, warn about the failure.
- What varied between repetitions (the skill's inputs) and what never
  varied (constants; hardcode them).
- The order things actually happened in; that is the draft `--steps`
  chain.

Ask the user only what the transcript cannot answer.

## From scratch

No material yet, so make some. Five questions before any scaffold:

1. What result does the user get, concretely: a file, a message, a
   fixed repo?
2. Which words would they say when they want it? That is the
   description.
3. What inputs does it need each time?
4. What does done look like, checkably? Those are verify conditions.
5. Which failure is unacceptable? That is where freedom narrows:
   script it or gate it.

Then build the smallest skill that produces the result, and grow it
from real runs (that is what learn is for), not from speculation.
