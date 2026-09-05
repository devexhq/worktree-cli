---
name: wt-code
description: >-
  Implement the approved plan in .agentic/plan.md for worktree-cli, running only
  scoped tests while building and the full gate suite (tests with coverage,
  ruff, basedpyright, complexity) once implementation is complete, without ever
  committing or pushing. Invoked as /wt-code to implement the plan, or /wt-code
  review to address the findings in .agentic/review.md. Use when asked to
  implement a plan, write the code for a planned change, or fix review findings.
---

# wt-code

Turn `.agentic/plan.md` into working code, or in review mode, turn `.agentic/review.md` findings into fixes.

## Modes

| Invocation | Input | Job |
|---|---|---|
| `/wt-code` | `.agentic/plan.md` | Implement the plan |
| `/wt-code review` | `.agentic/review.md` | Fix the review's Blocking findings |

If the input file is missing, stop and say so. Do not reconstruct a plan from the conversation, and do not implement from memory of what was discussed: run `/wt-plan` first.

## Hard boundaries

- **Never commit, stage, push, or touch PR state.** Not at the end, not "to be safe", not even when the gates pass. `/wt-push` owns that.
- **Never run the full gate suite mid-implementation.** Scoped tests only until the work is complete (see below).
- **The plan's contracts are binding.** Field names, types, defaults, flag names, exit codes, and message strings written as literal code in the plan are normative. Do not improve, rename, or extend them.
- **Do not implement anything the plan marks out of scope or flags as a trap.**

## Implementation loop

Work one FR (or one testable clause) at a time, in the plan's order. For each:

1. Re-read the plan section, then re-read the current contents of every file you are about to touch.
2. Write the production code, following the plan's artifact inventory for exact paths: domain types in `core/<domain>/models.py`, imperative operations in `core/<domain>/services/<verb>.py`, the domain's public entry point in `facade.py`, command handlers in `cli/<name>/commands/`, one `*Formatter` class per module under `cli/ui/formatters/<domain>/`.
3. Write the tests the plan names, at the tier it names, asserting the exact contract it states.
4. Run **only the scoped tests** for what you just touched:

   ```bash
   python -m pytest tests/<mirrored-path> -q          # one file or directory
   uv run inv test --no-parallel --fast-fail          # only when a whole-suite signal is genuinely needed
   ```

5. Fix what fails before moving to the next FR. Do not accumulate red tests across FRs.

Replace superseded code paths and update their callers in the same change set. Do not leave a compatibility shim, alias, or dual path behind unless the plan demanded one.

Apply the doc updates the plan's Cross-cutting section lists, and only those.

### When the plan is wrong

The plan was reviewed by a human, so a contradiction is worth surfacing rather than silently resolving. If a contract in the plan cannot be implemented as written, or grounding turns out to be stale (a cited symbol moved or does not exist), stop that FR, report what the plan says versus what the tree shows, and flag it with 🚨. Implement the rest. Never redesign a contract on your own and never widen scope to make one fit.

## Completion gate

Run this **once, after implementation is complete**, in this order. Each command's fix belongs in the code, never in a suppression or a lowered threshold:

```bash
ruff format .
ruff check .                                                          # ruff check --fix . for safe fixes
basedpyright src --level error                                        # must be 0 errors
uv run inv complexity --paths <changed-py-files> --plain --failed     # no touched function over 10
uv run inv test -c                                                    # full suite + coverage, fail_under 80%
```

Notes that decide whether a gate really passed:

- A bare `# type: ignore` suppresses nothing in this repo. Fix the type. A `# pyright: ignore[reportRuleName]` is a last resort and needs a one-line reason naming one of the three permitted cases in `code-conventions.md`.
- Over complexity 10, decompose into named helpers. Never raise the threshold.
- Coverage is a regression backstop. Do not write tests to lift the percentage, and read a coverage drop from deleting dead code as a success.
- If `ruff format` rewrites files, re-run the tests it touched.

Loop until every gate is green, then report: what was implemented per FR, the gate results, any 🚨 deviations, and the fact that nothing was committed or pushed.

## Review mode (`/wt-code review`)

1. Read `.agentic/review.md`. If it is absent, stop and say so.
2. Fix every **Blocking** finding. Address **Suggestions** only if the user asks or they passed in "--all"; leave **Nits** alone unless you are already editing that line.
3. Re-read each cited file before editing it, since the review may describe a state that has since changed.
4. Dispute rather than comply when a finding is wrong: state the finding, why it does not hold, and flag it 🚨 for the human. A finding you cannot verify in the code is not a finding.
5. Run the same completion gate above once the fixes are in.
6. Do not edit or delete `.agentic/review.md` or its machine-readable mirror `.agentic/review.json`. They are the reviewer's artifacts, and the next round is compared against them.

Report each finding as fixed, disputed, or deferred, with the `path:line` you changed.
