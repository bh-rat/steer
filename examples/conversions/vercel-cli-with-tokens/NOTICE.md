# Notice

This skill is a rebuild of `vercel-cli-with-tokens` from
vercel-labs/agent-skills, restructured on the steer framework as a
conversion study.

License provenance: the source repository's README declares MIT and its
package manifests carry `"license": "MIT"`, but the repository ships no
LICENSE file at its root. Confirm with the source before redistributing
this rebuild.

Changes from the original:

- The token discovery cascade (env, then `.env` under the expected
  name, then `.env` under another name, then ask the user) now starts
  with `steer secrets check`, which resolves environment, OS keychain,
  and steer's secret store in one command, and ends with
  `steer secrets set` so discovery happens once instead of every
  session. Tokens found in `.env` are detected by NAME only; the
  original's `grep -i 'vercel' .env` printed token values into the
  conversation transcript.
- The project/team binding (team slug, org id, project id) persists in
  `steer store` at workspace scope; the original rediscovered it every
  run.
- Environment recon (CLI installed? git remote present?) goes through
  `steer context --tools vercel,node,npm` instead of ad-hoc checks.
- Troubleshooting, domains, and Stripe Projects plan sections moved to
  `references/`, loaded only when that branch is hit.
- A lesson capture loop (`steer learn`) was added.
- Em dashes in carried-over prose were replaced with plain punctuation;
  one "Important" note and the working agreement gained a rule about
  never printing credential values.
- `license` and `metadata.version` added to the frontmatter;
  `metadata.author: vercel` removed since this rebuild is not by Vercel
  (the derivation is recorded here instead).
