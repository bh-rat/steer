# License triage and attribution

Do this before touching anything else. Per skill, not per repo: one
repository can mix permissive and proprietary skills in the same tree.

## Where the license hides

1. `LICENSE.txt` / `LICENSE` inside the skill directory itself.
2. A `license:` field in the SKILL.md frontmatter.
3. The repository root LICENSE.
4. A claim in the README with no license file anywhere (weakest).
5. Nothing at all.

## The four outcomes

| Finding | What to do |
|---|---|
| Permissive with a license file (MIT, Apache-2.0, BSD) | Proceed. Copy the license file into the rebuild as LICENSE.txt. Write NOTICE.md (below). Apache-2.0 additionally requires stating the changes; the NOTICE change list satisfies it. |
| Permissive by README claim only, no license file | Proceed locally, but flag it: the rebuild must not be redistributed until the claim is confirmed with the source. Record the provenance gap in NOTICE.md. |
| Share-alike (CC-BY-SA and kin) | Warn the user before starting: the rebuild must carry the same license, which may not fit the destination repo. |
| Proprietary, all-rights-reserved, no-derivatives, or NO license at all | Stop and tell the user. No license means no permission. A clean-room reimplementation is a different task with different rules; do not copy anything. |

## NOTICE.md, the conversion record

Every rebuild carries a NOTICE.md stating:

- what it is a rebuild of (project and skill, with the license named
  and where its text lives),
- every deliberate delta from the original, one bullet each: machinery
  swapped for components, files moved or dropped, wording changed,
  frontmatter added or removed,
- any provenance caveat (missing license file, ambiguous terms).

## Frontmatter honesty

- Keep the original's `description` (it is the trigger) unless it
  lacks "use when" phrasing; append, do not rewrite.
- Add `license:` and `metadata.version` if absent.
- Drop authorship claims that stop being true on a rebuild
  (`metadata.author` naming the original vendor); the derivation
  lives in NOTICE.md instead.
