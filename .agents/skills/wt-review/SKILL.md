---
name: wt-review
description: >-
  Review a change set in the worktree-cli repo on three axes, fidelity to the
  plan, implementation quality, and adherence to every rule in AGENTS.md and
  docs/agents/*.md, then write the verdict to .agentic/review.md plus a
  machine-readable .agentic/review.json. Runs no tests
  or tooling. Use when asked to review a pull request, local pending changes, or
  commits on a branch, to run a pre-commit review gate, or to check whether a
  change obeys or should have updated the agent docs. Invoked as /wt-review
  [<pr-number>] [--post]. Runs in GitHub Copilot CLI, Gemini CLI, and any Agent
  Skills client.
---

# wt-review

Review a change set in `worktree-cli` on three axes:

1. **Plan fidelity**: does the code implement `.agentic/plan.md`'s contracts, no more and no less.
2. **Implementation**: does the code hold up (correctness, layering, typing, tests).
3. **Doc adherence**: does it obey every directive in `AGENTS.md` and `docs/agents/*.md`, and does it update the docs this change was required to update.

Output goes to `.agentic/review.md`, which `/wt-code review` consumes.

## Hard boundaries

- **Never run tests or tooling.** No `inv test`, no `pytest`, no `ruff`, no `basedpyright`, no `inv complexity`. `/wt-code` owns the gate; a review that leans on tool output stops reading the code. Read-only `git` and `gh` are the only commands you need.
- **Never edit, stage, commit, or push.** Report findings and hand off. `/wt-code review` applies the fixes.
- **Never approve on absence of evidence.** A rule you did not check is not a rule that passed.

## 1. Resolve the diff scope

Resolve in this order and review only that range:

| Input | Scope | Inspect with |
|---|---|---|
| PR number given | that PR's range | `gh pr view <n> --json baseRefName,headRefName,title,body`, then `git fetch origin` and `git diff origin/<base>...origin/<head>` |
| Working tree dirty | uncommitted work | `git status --porcelain`, `git diff`, `git diff --staged`, plus full contents of untracked files in scope |
| Clean tree | commits on this branch | `git diff origin/<default>...HEAD` (resolve the default branch with `gh repo view --json defaultBranchRef`) |

Record the changed-file list. If the scope is empty, say so and stop.

## 2. Load the standards yourself

Do not review from memory of this repo. Read:

- `AGENTS.md`, the authority and the index of which doc governs what
- the always-on docs it names: `docs/agents/architecture.md`, `docs/agents/code-conventions.md`, `docs/agents/schemas.md`, `docs/agents/glossary.md`, `docs/agents/testing.md`
- whichever conditional doc each tripped gate names (see [doc-adherence.md](doc-adherence.md))
- `.agentic/plan.md` if it exists, as the change's contract

When a doc's claim about a model, field list, or enum drives a finding, spot-check the source file first. Docs here are allowed to be stale; source is not.

## 3. Check plan fidelity

Skip this axis only when `.agentic/plan.md` is absent, and say so in the report.

- Every FR in the plan has landed, and every artifact row has its file.
- Contracts match **exactly**: field names, types, defaults, `status` values, flag names, help copy, exit codes, and error, warning, and fix strings. A "better" name than the plan's is a finding, since the plan was human-reviewed.
- Nothing landed that the plan marked out of scope or named as a trap.
- Every planned test exists, at the planned tier, asserting the stated contract.
- Where the code deviates, the deviation was surfaced rather than absorbed silently.

## 4. Sweep the mechanical rules

The rules that get missed are the ones no linter enforces, and they are missed because reviewers read for design and skim identifiers. So do this as an explicit pass, not a byproduct.

Walk [conventions-checklist.md](conventions-checklist.md) against the changed hunks. It enumerates every hand-checked rule from `code-conventions.md`, `testing.md`, and `architecture.md`.

Two passes that must be deliberate:

- **Every new or changed identifier**, in production and tests: locals, parameters, attributes, fixtures, loop variables. A cryptic truncation is a `code-conventions.md` violation regardless of how obvious it reads in context. `buf` must be `buffer`, `res` must be `result`, `err_msg` must be `error_message`.
- **Every new test**: name format and outcome, tier, mocking policy, and whether it asserts a contract or an implementation detail.

Each finding names the rule and the doc it comes from. If you cannot cite a rule, it is a Suggestion or a Nit, not Blocking.

## 5. Check doc adherence

Work through [doc-adherence.md](doc-adherence.md) with the changed-file list. It maps each kind of change to the directive it must satisfy and the doc that must have been updated in the same change.

A missing required doc update is **Blocking**. A doc update that was not required (a feature essay appended to `architecture.md`, a field table duplicating what a `Read` of the source already shows) is a **Suggestion** to delete it.

## 6. Judge what you cannot run

You are not running the gates, so reason about them from the diff instead and mark each as a risk rather than a result:

- Functions whose nesting or `elif` chains look likely to exceed cognitive complexity 10.
- Suppressions and `Any` annotations that would let `basedpyright --level error` pass while hiding a real error.
- Branches with no covering test, especially in a factory or dispatch chain.

Say `not run by this skill` for anything you are inferring. Never report an inference as a gate result.

## 7. Write the report

Write this to `.agentic/review.md` (create `.agentic/` if needed), overwriting any previous round, and echo the verdict plus the Blocking list in chat:

```markdown
## wt-review - round <n>

**Verdict:** APPROVE | CHANGES REQUIRED
**Scope:** <PR #n | uncommitted | origin/<default>...HEAD> (<k> files)
**Plan:** `.agentic/plan.md` <sha or "absent">

### Blocking
- `path:line` - what is wrong, the rule it breaks (`<doc>#<section>`), and the concrete fix.

### Suggestions
### Nits

### Plan fidelity
- <FR-n> - implemented as specified | deviates: <what> | missing

### Doc adherence
- <gate tripped> - satisfied | missing update to <doc> | not applicable

### Unverified
- Gates were not run by this skill. Risks read from the diff: <complexity, coverage, typing risks, or "none">
```

Severity: **Blocking** is a defect, a broken user-facing contract, a deviation from a plan contract, a suppression hiding a real type error, a test asserting implementation, a violation of a stated doc rule, or a missing required doc update. **Suggestion** is a real improvement that need not land now. **Nit** is style or wording with no rule behind it. Say `APPROVE` only with zero Blocking items. An empty section stays, marked `none`.

With `--post` and a PR scope, post the same content as a comment review: `gh pr review <n> --comment --body-file .agentic/review.md`. Never `--approve` or `--request-changes`, and do not add reviewers.

On `CHANGES REQUIRED`, hand off to `/wt-code review`, which reads `.agentic/review.md`. Re-run this skill afterward as round n+1 against the updated scope. Cap at 3 rounds, then hand the remainder to the human.

## 8. Emit the machine-readable verdict

Write `.agentic/review.json` alongside the markdown, and print the same object as the **last line of stdout**, minified onto one line. A caller decides the next step from this file alone, without parsing prose.

```json
{
  "verdict": "CHANGES_REQUIRED",
  "round": 1,
  "scope": { "kind": "pr", "ref": "364", "files": 7 },
  "plan": ".agentic/plan.md",
  "counts": { "blocking": 2, "suggestions": 3, "nits": 1 },
  "findings": [
    {
      "severity": "blocking",
      "path": "src/worktree/core/diff/services/render.py",
      "line": 42,
      "rule": "code-conventions.md#variable-naming",
      "summary": "Local named `buf`; cryptic truncation of `buffer`."
    }
  ]
}
```

Field contracts, since this is what a loop branches on:

- `verdict` is exactly `APPROVE` or `CHANGES_REQUIRED`. Underscored, unlike the markdown heading, so it survives shell and condition matching untouched.
- `verdict` is `APPROVE` if and only if `counts.blocking` is `0`. Never emit one without the other.
- `scope.kind` is `pr`, `uncommitted`, or `branch`. `scope.ref` is the PR number, an empty string, or the compared range.
- `plan` is the plan path, or `null` when `.agentic/plan.md` was absent.
- `findings` carries every Blocking item and may omit Suggestions and Nits; `counts` always reflects the full report. `rule` is `<doc>#<section>` for anything Blocking, and `null` only for a Suggestion or Nit.
- `line` is an integer, or `null` for a file-level or repo-level finding.

Keep this shape stable. It is the contract a driver script consumes today, and the `outputs` condition a `wt` blueprint will branch on later (`outputs` conditions parse a step's stdout as JSON), so a field renamed here breaks both.

## Independence

If this same session wrote the code, re-derive every finding from the diff and the docs, and ignore in-session claims that something was already verified or intentional. For a genuinely independent pass, run the skill in a fresh session: `copilot -p "use wt-review on PR <n>"` or `gemini -p "use wt-review on PR <n>"`.
