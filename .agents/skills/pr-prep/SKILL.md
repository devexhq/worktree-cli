---
name: pr-prep
description: >-
  Review the current uncommitted worktree-cli changes and draft
  .agentic/commit-msg, .agentic/pr-title, and .agentic/pr-description, then
  hand off to `uv run python scripts/pr.py` to commit, push, and open (or
  reuse) the pull request. Invoked as /pr-prep. Use when asked to prep a
  commit and PR, draft PR text from the working tree, or stage a
  commit+push+PR handoff.
---

# pr-prep

Turn the current uncommitted diff into three drafted text files, then run
`scripts/pr.py` to commit, push, and open the PR. This skill only writes the
drafts and invokes the script; the script does the git/gh work.

## Step 1: Read the diff

```bash
git status --porcelain
git diff
git diff --staged
git rev-parse --abbrev-ref HEAD
```

If there is nothing uncommitted and nothing staged, say so and stop — there is
nothing to prep.

Read enough of the actual diff to describe it accurately. Do not draft from
file names alone.

## Step 2: Draft the handoff files

Create the directory if needed and write:

```bash
mkdir -p .agentic
```

- **`.agentic/commit-msg`** — full commit message: an imperative, semantic
  title line (`feat(ui):`, `fix(config):`, `refactor(cli):`, `docs:`,
  `test:`, ...), a blank line, then a short wrapped-prose body explaining what
  changed and why. No file-by-file listing.
- **`.agentic/pr-title`** — a single line, same imperative/semantic style as
  the commit title. Can match it exactly.
- **`.agentic/pr-description`** — the three-section format from
  `docs/agents/git-and-pr-conventions.md`:

  ```markdown
  ## Why

  <Context and motivation, 2-3 short sentences.>

  ## Approach

  - <Key technical decision or implementation detail, 1-2 sentences.>
  - <...>

  Fixes #<n>
  ```

  Omit the `Fixes #N` line entirely when there is no related issue — never
  invent one.

No AI attribution or tool co-author trailers in any of these three files, per
`docs/agents/git-and-pr-conventions.md`.

Show the drafted contents to the user before proceeding, since Step 3 commits
and pushes real changes.

## Step 3: Run the handoff script

```bash
uv run python scripts/pr.py
```

This stages the uncommitted changes, commits with `.agentic/commit-msg`,
creates a feature branch first if `HEAD` is still on the default branch,
pushes, and then creates a new PR or reports the already-open one for this
branch — reading `.agentic/pr-title` and `.agentic/pr-description` for the PR.
On success it deletes the three handoff files; on failure it leaves them in
place so a re-run doesn't require redrafting.

To stage only specific paths instead of everything uncommitted, pass them
through: `uv run python scripts/pr.py path/one path/two`.

## Hard boundaries

- **Never hand-run `git commit` / `git push` / `gh pr create` yourself in this
  skill.** Draft the files, then let `scripts/pr.py` do the git/gh work, so
  there is one code path for it.
- **Never run tests or tooling** (`inv test`, `ruff`, `basedpyright`, `inv
  complexity`). This skill packages what's already there; it doesn't gate it.
- **Never edit code** while drafting. If the diff looks wrong or mixes
  unrelated concerns, say so and ask before drafting, since this repo
  requires one fix or feature per PR.
- **Don't add reviewers** or PR labels unless the user names them.

## Report

State what was drafted (paraphrase, don't just repeat the files verbatim),
then report the script's output: branch created (if any), commit SHA, push
result, and the PR URL. Note that no tests or tooling were run.
