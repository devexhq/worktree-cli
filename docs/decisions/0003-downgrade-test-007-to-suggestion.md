# 0003. Downgrade TEST-007 to SUGGESTION and delete its scanner

- Status: Accepted
- Date: 2026-09-16
- Driven by: direct maintainer instruction to relax the piecewise-result-assertion rule and,
  once it was no longer a BLOCKER, to delete the scanner that had backed it.

## Context

`TEST-007` ("No Unasserted Fields on the Result Under Test") has been a BLOCKER since
[0001-test-doctrine-phase-0.md](0001-test-doctrine-phase-0.md), which in D5 explicitly chose to
fix `tests/lint/test_assertion_style.py`'s class-scanning bug rather than delete the scanner,
citing `CI-004` (Mechanical Enforcement Parity): a BLOCKER rule that is mechanically checkable
must have an executing check. That fix landed and the scanner ran clean (modulo its
`SCANNER_BURN_DOWN` allowlist) since.

The instruction driving this ADR came in two steps. First: stop treating a piecewise or
`exclude`-weakened result assertion as a `wt-review` BLOCKER — whole-object comparison via
`assert_model_equal` remains the documented, recommended style, but a violation becomes a
code-quality suggestion rather than a merge-blocking defect. That step was landed keeping the
scanner file in place, on the reasoning that `CI-004` still applied. Once `TEST-007` was no longer
BLOCKER, `CI-004`'s own guideline no longer required a mechanical check for it ("A BLOCKER rule
that can be checked mechanically must have an executing check" — conversely, a non-BLOCKER rule
carries no such obligation), and the maintainer's second instruction was to delete the now-optional
scanner outright rather than keep dead weight in the suite.

## Decision

**Was:** `TEST-007` severity `BLOCKER`, mechanically enforced by
`tests/lint/test_assertion_style.py` (`AssertionStyleTests`), which walked every collected test
file for piecewise attribute access on a result variable, allowlisting nine known-mismarked files
in `SCANNER_BURN_DOWN`.

**Now:** `TEST-007` severity `SUGGESTION`. `tests/lint/test_assertion_style.py` is deleted, along
with `SCANNER_BURN_DOWN` and its nine entries. The rule itself, its guideline text, and its
`positive_example`/`negative_example` remain in `rules_spec.yaml` as documented guidance — whole-
object comparison is still the right pattern to write and to suggest in review — but nothing in
`tests/lint/` checks it mechanically anymore. A piecewise result assertion is now caught (or not)
at `wt-review` time as a Suggestion, same as any other stylistic finding with no dedicated
scanner.

`exclude` still does not exist as an `assert_model_equal` parameter (D3, unaffected): that removal
was a production API change, not an assertion-style lint concern, and stands independent of this
scanner's fate.

**Rejected:**
- *Keep the scanner running as a passive, rule-less convention check, the way
  [0002-simplify-cli-test-doctrine.md](0002-simplify-cli-test-doctrine.md) kept
  `tests/lint/test_marker_taxonomy.py` after `TEST-016` was dropped* — that precedent applied
  when a rule was deleted entirely, per explicit instruction not to delete the file on that
  ticket. Here the rule is not deleted, only downgraded, and the explicit instruction on this
  ticket was to delete the file. Nothing forces the two prior scanner-fate decisions
  (`test_marker_taxonomy.py`, `test_assertion_style.py`) to resolve the same way.
- *Leave `TEST-007` as BLOCKER and instead have `wt-review` ignore `TEST-007` findings* — this
  would desynchronize `rules_spec.yaml` (the source of truth `REVIEW_CHECKLIST.json` is compiled
  from) from actual review behavior, which is exactly the drift `DOC-008` and `CI-004` exist to
  prevent. Changing the rule's own `severity` field keeps `rules_spec.yaml`, the compiled
  checklist, and `wt-review`'s behavior in the same state.

## Collateral edits this downgrade and deletion force

None of these are further policy reversals; they correct rule-provenance text and illustrative
examples that named `TEST-007` or its scanner specifically as a BLOCKER-severity, mechanically-
enforced exemplar, which would otherwise contradict the new `rules_spec.yaml` state (`DOC-008`):

- `docs/agents/rules_spec.yaml`'s `planner_rules` entry `PLAN-016` cited `TEST-007` rows as
  `BLOCKER` in its `positive_example`/`negative_example` Rule Evaluation Matrix illustrations;
  both rows now read `SUGGESTION`, matching the new severity.
- `docs/agents/rules_spec.yaml`'s `CI-004` guideline previously used
  `# TEST-007 enforced by tests/lint/test_assertion_style.py` as its `positive_example` of "a
  BLOCKER rule with an executing check." Since `TEST-007` is no longer BLOCKER and its scanner is
  deleted, that example no longer illustrates `CI-004`'s own requirement; it is repointed at
  `ARCH-001`/`tests/lint/test_import_boundaries.py`, a still-BLOCKER, still-enforced pairing —
  the same repointing pattern 0002's D4 used when `TEST-016` was dropped. `CI-004`'s
  `decision_log` field now points here instead of 0001's D5, since D5's outcome (fix, don't
  delete) is what this ADR partially reverses.
- `docs/agents/planning.md`'s worked Rule Evaluation Matrix example and
  `.agents/skills/wt-plan/SKILL.md`'s and `.agents/skills/wt-review/SKILL.md`'s worked matrix
  examples all had hardcoded `TEST-007 | ... | BLOCKER | ...` rows; all now read `SUGGESTION`.
- `.agents/skills/wt-review/SKILL.md`'s severity-classification list named "piecewise or
  `exclude`-weakened result assertions" under its `BLOCKER` bullet; moved to the `SUGGESTION`
  bullet.
- [0001-test-doctrine-phase-0.md](0001-test-doctrine-phase-0.md)'s D5 amended with a forward
  pointer here; D5's "fix it, not delete it" outcome no longer describes the current state, since
  the fixed scanner has since been deleted once its backing rule dropped below BLOCKER.
- Compiled artifacts (`docs/agents/REVIEW_CHECKLIST.json`, `docs/agents/PLANNER_RULES.md`, and the
  four package `docs/RULES.md` files) regenerated via `uv run python scripts/compile_rules.py`.

## Rule IDs touched

`TEST-007` (severity BLOCKER → SUGGESTION; scanner deleted), `CI-004` (example and decision_log
correction only, not a policy reversal).

## Consequences

- `wt-review` no longer rejects a change for a piecewise or waived-field result assertion;
  `TEST-007` findings are now Suggestions, same tier as other constructive-improvement findings.
- `tests/lint/test_assertion_style.py` and `SCANNER_BURN_DOWN` are gone. The nine files that
  allowlist tracked (`tests/cli/commands/test_catalog.py`, `tests/core/catalog/test_catalog.py`,
  `tests/core/runtime/test_loop_runner.py`, `tests/core/sandbox/test_patch.py`,
  `tests/core/sandbox/test_squash.py`, `tests/core/step/test_process_group.py`,
  `tests/core/step/test_runner_assertions.py`, `tests/core/step/test_runner_retry.py`,
  `tests/core/step/test_step.py`) are no longer mechanically flagged for piecewise assertions;
  remediating their assertion style, if ever done, is now a `wt-review`-time judgment call rather
  than a scanner-tracked burn-down.
- `tests/lint/` shrinks by one module; the remaining six (`astlib.py`, `__init__.py`,
  `test_import_boundaries.py`, `test_output_routing.py`, `test_remediation_text.py`,
  `test_result_contracts.py`) are unaffected.
