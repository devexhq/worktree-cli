# Git and PR Conventions

When creating commits or pull requests for this repository:

- Do **not** add `Co-authored-by: Cursor` or any other AI/agent co-author trailer.
- Do **not** add "Made with Cursor" (or similar tool attribution) to commit
  messages or PR descriptions.
- Use semantic, human-readable commit messages and PR text only.

If asked to commit or open a PR, verify the commit message body has no agent
attribution before finishing.

## Branches and merges

- Branch names follow `<username>/<short-description>` (e.g. `ljb/refactor-tests`).
- PRs are merged via merge commits, not squashed.

## PR scope

Prefer one fix or one concern per PR, even during larger refactors:

- A change that touches many files because it mechanically renames/moves one
  thing (e.g. a schema merge) can still be one PR — but a PR that mixes that
  mechanical change with unrelated cleanup, new features, or multiple
  unrelated bug fixes should be split.
- When a review turns up several distinct findings (e.g. a code review report
  listing many separate issues), open one PR per finding rather than
  bundling them, even if the fixes are individually small. Small,
  narrowly-scoped PRs are faster to review and safer to revert.
- If a task naturally decomposes into "land the model/schema change",
  "update the callers", and "delete the old path", prefer that as sequential
  PRs over one large one, unless the intermediate states would leave the
  codebase broken.

## GitHub issues

For opening or revising issues (required sections, tone, skeleton), see
[github-issues.md](github-issues.md).
