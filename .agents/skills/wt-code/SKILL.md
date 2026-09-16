---
name: wt-code
description: >-
  Implement the approved plan in .agentic/plan.md for worktree-cli consulting
  domain-scoped RULES.md, running only scoped tests while building and the full gate
  suite (tests with coverage, ruff, basedpyright over src and tests, complexity, marker
  taxonomy) once implementation is complete, reporting observed gate numbers rather than
  documented thresholds, and never committing or pushing. Invoked as /wt-code to implement
  the plan, or /wt-code review [--fix blockers|warnings|suggestions|all] to address the
  findings in .agentic/review.md. Use when asked to implement a plan, write the code for a
  planned change, or fix review findings.
---

# wt-code

Turn `.agentic/plan.md` into working code, or in review mode, turn `.agentic/review.md` findings into fixes.

## Modes

| Invocation | Input | Job |
|---|---|---|
| `/wt-code` | `.agentic/plan.md` | Implement the plan |
| `/wt-code review [--fix <scope>]` | `.agentic/review.md` | Fix review findings (`blockers`, `warnings`, `suggestions`, `all`) |

If the input file is missing, stop and say so. Do not reconstruct a plan from the conversation, and do not implement from memory of what was discussed: run `/wt-plan` first.

## Hard boundaries

- **Never commit, stage, push, or touch PR state.** Not at the end, not "to be safe", not even when the gates pass. `/wt-push` owns that.
- **Never run the full gate suite mid-implementation.** Scoped tests only until the work is complete.
- **The plan's contracts are binding.** Field names, types, defaults, flag names, exit codes, and message strings written as literal code in the plan are normative. Do not improve, rename, or extend them.
- **Do not implement anything the plan marks out of scope or flags as a trap.**
- **Never create a test file the plan's test ledger does not list** (`PLAN-013`), and never skip a deletion the deletion ledger lists (`PLAN-009`). Both directions are contract breaches, and the additive direction is the one that slips through unnoticed.
- **A green gate is not evidence that a check ran.** Report what each gate observed, never what a doc says it enforces.

## Implementation loop

Before writing or refactoring any code:
1. Identify the target domain and load its `RULES.md`, which carries both cross-cutting repo rules and package-specific invariants:
   - `core/`: `src/worktree/core/docs/RULES.md`
   - `common/`: `src/worktree/common/docs/RULES.md`
   - `cli/`: `src/worktree/cli/docs/RULES.md`
   - `tests/`: `tests/docs/RULES.md`
2. Read that file before editing anything in the domain, not after a failure.
3. Follow the positive patterns defined for the file's scope (`ARCH-*` for `core/`, `RENDER-*` for formatters, `MODEL-*` for DTOs, `PERF-*` for queries, `TEST-*` for `tests/`).

Work one FR (or one testable clause) at a time, in the plan's order. For each:

1. Re-read the plan section, then re-read the current contents of every file you are about to touch.
2. Write the production code, following the artifact inventory for exact paths: domain types in `core/<domain>/models.py`, imperative operations in `core/<domain>/services/<verb>.py`, the domain entrypoint in `<domain>.py`, command handlers in `cli/<name>/commands/`, one `*Formatter` class per module under `cli/ui/formatters/<domain>/`.
3. Write the tests the ledger names, at the path it names, with the marker it names, asserting the exact contract it states.
4. Run only the scoped tests for what you just touched:

   ```bash
   python -m pytest tests/<mirrored-path> -q          # one file or directory
   uv run inv test --no-parallel --fast-fail          # only when a whole-suite signal is genuinely needed
   ```

5. Fix what fails before moving to the next FR. Do not accumulate red tests across FRs.

Execute the deletion ledger as you go, in the same change set as the code that supersedes each entry. Replace superseded code paths and update their callers. Do not leave a compatibility shim, alias, or dual path behind unless the plan demanded one (`COMPAT-002`, `COMPAT-003`), and never leave a negative existence test behind as the record of a removal (`TEST-009`).

Apply the doc updates the plan's cross-cutting section lists, and only those.

### Writing tests

Four things to get right that the plan states but is easy to drop while typing:

- **Declare the module's primary marker** (`TEST-016`). `pytestmark = pytest.mark.<marker>` at module level, or per class when the plan says the module mixes tiers. An unmarked module is invisible to every marker-filtered run, which means it is invisible to CI selection even while it passes locally. `--strict-markers` catches a misspelled marker, never a missing one.
- **Assert machine-readable surfaces only** (`TEST-001`, `TEST-017`). Exit codes, `--format json` payloads compared as whole dicts, `BaseResult` objects compared whole, file and git state. Never assert a panel title, status label, field caption, prose sentence, glyph, or column padding from `res.stdout`. If the contract you need to pin is what a view renders, it belongs in that view's formatter test, where the render assertion checks a value from the view model rather than a caption (`TEST-012`), captured through `render_rich` at width 160.
- **Assert every field of the result under test** (`TEST-007`). Name every field on the expected side; there is no `exclude` parameter, and a field left to its default is rejected. When a value will not match, fix the seam before reaching for a waiver: inject the clock or id factory (`TEST-011`) so the value is a literal you can state. Only for a value you genuinely cannot own (a real git SHA, an OS pid, a database-minted id) use a matcher at that field's position, and build the expected object with `model_construct`, since the plain constructor rejects a matcher under `strict=True`.
- **Register spawned processes with the harness registry and use the shared poll helper** (`TEST-011`). No open-coded poll loop and no bare `time.sleep` in a test body; the harness owns the poll interval and deadline, and registration is what stops a failing test from leaking a process group.

### Writing enforcement code

Required by `CI-004`. A test whose assertion is "no violations found" passes when it inspects nothing, so it must prove it can fail:

1. Assert the collected input set is non-empty before asserting the violations list is empty. A scanner whose glob, path prefix, or AST traversal silently matches nothing is the most common way an invariant test becomes decorative.
2. Ship the negative fixture test the plan names: construct a violating sample, assert the checker flags it. The fixture must match the real shape it polices. A checker proven only against a module-level function does not prove anything about the `*Tests` classes this suite actually uses, since an AST walk over `tree.body` alone never descends into a class.
3. Before declaring the check done, break it on purpose once: temporarily introduce the violation into a real file in the tree, confirm the check fails, then revert. An enforcement test you have never watched fail is unverified.
4. If the check lands green only because of a burn-down allowlist of known violators, the allowlist is explicit, each entry is justified, and it only ever shrinks. Adding an entry to make a new violation pass defeats the check.

### When the plan is wrong

The plan was reviewed by a human, so a contradiction is worth surfacing rather than silently resolving. If a contract cannot be implemented as written, if grounding turns out to be stale (a cited symbol moved or does not exist), or if a doc the plan relies on names a helper that is not in the tree, stop that FR, report what the plan says versus what the tree shows, and flag it with 🚨. Implement the rest. Never redesign a contract on your own and never widen scope to make one fit.

If the plan's ledger asks for a test whose contract you find already pinned elsewhere while implementing, say so with both paths and 🚨 rather than writing the duplicate. Duplicated contracts are the cost the reviewer cannot see.

## Completion gate (`CI-001`)

Run this once, after implementation is complete, in this order. Each command's fix belongs in the code, never in a suppression or a lowered threshold:

```bash
ruff format .
ruff check .                                                          # ruff check --fix . for safe fixes
basedpyright src tests --level error                                  # must be 0 errors, tests included
uv run inv complexity --paths <changed-py-files> --plain --failed     # no touched function over 10
uv run python -m pytest -m "not (unit or integration or cli or invariant)" --collect-only -q
uv run inv test -c                                                    # full suite with coverage
```

Then read what the gates actually enforce, rather than what the docs claim:

```bash
uv run python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['tool']['coverage']['report']['fail_under'])"
git diff --stat -- tests/ | tail -1
```

Notes that decide whether a gate really passed:

- **`basedpyright` covers `src tests`**, matching `[tool.basedpyright].include` and `CI-001`. Narrowing it to `src` leaves the harness and fixtures unchecked, which is exactly where loose typing accumulates, and it makes `TEST-014` unenforceable by the very gate that is supposed to carry it.
- **The marker query must collect zero tests** (`TEST-016`). Anything it collects is a module with no primary marker, and it will silently drop out of every filtered run.
- **Coverage: report the observed percentage and the configured `fail_under`, both.** If `fail_under` is `0`, the coverage gate passed because it is switched off. Say that plainly rather than reporting a pass, never add tests to lift the number, and never lower the configured floor to make a commit pass (`CI-001`).
- **Report the `tests/` line delta** against the plan's budget (`PLAN-017`). Growth is expected when the ledger says so and suspicious when it does not. A change that adds thousands of test lines against a plan budgeted in the hundreds is a finding you owe the reviewer.
- A bare `# type: ignore` suppresses nothing in this repo. Fix the type. A `# pyright: ignore[reportRuleName]` is a last resort and needs a one-line reason naming one of the three permitted cases in `code-conventions.md`.
- Over complexity 10, decompose into named helpers. Never raise the threshold.
- If `ruff format` rewrites files, re-run the tests it touched.

Loop until every gate is green, then report, per gate, the command and the number it produced. For anything the repo does not actually enforce, say `not enforced (fail_under=0)` or `not run by any hook or CI step` instead of listing it as a pass (`CI-004`). A gate that cannot fail is not a gate, and reporting it as green is how a claimed threshold outlives its configuration.

Close the report with: what was implemented per FR, the deletions executed, the observed gate numbers, any 🚨 deviations, and the fact that nothing was committed or pushed.

## Review mode (`/wt-code review`)

1. Read `.agentic/review.md`. If it is absent, stop and say so.
2. Determine which findings to address from `--fix [blockers, warnings, suggestions, all]` or user instruction:
   - **`blockers`** (default): fix every `BLOCKER`. Leave `WARNING`, `SUGGESTION`, and `NIT` alone unless you are already editing that line.
   - **`warnings`**: fix every `BLOCKER` and `WARNING`.
   - **`suggestions`**: fix every `BLOCKER`, `WARNING`, and `SUGGESTION`.
   - **`all`**: fix all four tiers.
3. Re-read each cited file from disk before editing it, since the review may describe a state that has since changed.
4. A finding that says "delete this" is fixed by deleting it. Redundant tests (`TEST-004`), dead harness symbols (`TEST-013`), and duplicated contracts are resolved by subtraction, never by adding a comment explaining why the duplicate is fine.
5. Dispute rather than comply when a finding is wrong: state the finding, why it does not hold, and flag it 🚨 for the human. A finding you cannot verify in the code is not a finding.
6. For a fix to an enforcement defect (a check that did not check), watch it fail before you call it fixed: reproduce the violation the check missed, confirm the repaired check flags it, then revert the reproduction.
7. Run the same completion gate above once the fixes are in.
8. Do not edit or delete `.agentic/review.md` or `.agentic/review.json`. They are the reviewer's artifacts, and the next round is compared against them.

Report each finding as fixed, disputed, or deferred, with the `path:line` you changed.

## Rule provenance

Cite a rule ID only from this list. Each resolves to a rule in `docs/agents/rules_spec.yaml`, compiled into the domain `RULES.md` files and `REVIEW_CHECKLIST.json`.

| This skill's section | Rule IDs |
|---|---|
| Domain rules to load before editing | `ARCH-*`, `RENDER-*`, `MODEL-*`, `PERF-*`, `TYPE-*`, `TEST-*` by scope |
| Plan and ledger fidelity | `PLAN-009`, `PLAN-013`, `PLAN-017` |
| Deletions and no shims | `COMPAT-002`, `COMPAT-003`, `TEST-009`, `TEST-013` |
| Writing tests | `TEST-016`, `TEST-001`, `TEST-017`, `TEST-012`, `TEST-007`, `TEST-010`, `TEST-011`, `TEST-014` |
| Writing enforcement code | `CI-004` |
| Completion gate | `CI-001`, `TEST-014`, `CI-004` |

The mode split (`/wt-code` versus `/wt-code review`), the scoped-tests-only rule during implementation, and the prohibition on committing are skill-owned with no compiled rule: state them as this skill's directive rather than citing an ID.
