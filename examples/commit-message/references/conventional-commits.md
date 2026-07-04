# Conventional commit types: cheat sheet

Format: `type(scope): subject`. Imperative, ≤ 50 chars, no period.

| Type | Use for |
|---|---|
| `feat` | user-visible new capability |
| `fix` | user-visible bug fix |
| `refactor` | code change that is neither feat nor fix |
| `perf` | performance improvement |
| `docs` | documentation only |
| `test` | adding or correcting tests |
| `build` | build system, packaging, dependencies |
| `ci` | CI configuration |
| `chore` | maintenance that touches no src/test behavior |

Scope: the module or area touched (`auth`, `parser`, `deps`); omit when
it would just repeat the repo name.

Breaking change: add `!` after the type/scope (`feat(api)!: …`) **and** a
`BREAKING CHANGE:` paragraph in the body stating the migration.

Choosing between `fix` and `refactor`: if a user could have observed the
old behavior as wrong, it's `fix`; otherwise `refactor`.

Body: explain what and why; the diff already shows how. Wrap at 72.
