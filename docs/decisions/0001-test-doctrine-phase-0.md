# 0001. Test doctrine Phase 0: seven decisions

- Status: Accepted
- Date: 2026-09-16
- Driven by: `personal/review-plan.md` (09-16 test-suite review), landed in `rules_spec.yaml` via commit `fe9a473`

## Context

The 09-16 review found the test suite's documented doctrine (`testing.md`) and its merged
tests disagreeing on seven points. Each point had a "change the code" option and a
"change the rule" option. This record keeps the rejected options and the reasons visible,
so a future change to one of these rules has to argue against a known alternative rather
than rediscover it.

## D1. Dual-tier CLI: keep, collapse, or condition it

**Decided:** Conditional. `*CliIntegrationTests` mandatory per command action.
`*RootTests` required only when the handler owns logic the domain layer does not
(coercion, branch selection, interactive abort, multi-call composition). A pass-through
handler gets no root test, and a root test may never restate a `tests/core/` contract.

**Rejected:**
- *Keep mandatory* — would require root tests to assert only the handler's own
  composition, never a domain contract; harder to enforce mechanically than making the
  test optional in the first place.
- *Collapse to runner-only* — loses cheap unit coverage on a genuinely branchy handler
  (e.g. `config_set_command`'s string-to-bool/int coercion).

**Rule:** `TEST-004`. Cites `ConfigSetRootTests` (owns coercion, keeps its root test) as
positive and `ConfigShowRootTests` (pass-through, re-asserts `ConfigLoadResult` already
pinned in `tests/core/config/`) as negative — both drawn from the file that will need
remediation in Phase 2.

**Superseded:** Reversed by
[0002-simplify-cli-test-doctrine.md](0002-simplify-cli-test-doctrine.md) — the root-test mandate
is dropped; the runner-test matrix stays.

## D2. Human-readable output assertions in CLI runner tests

**Decided:** Ban, with a narrow exception for published error-code tokens.
CLI runner (Tier 3) tests assert exit code, `--format json` literal payloads, and disk
state only. A token like `CONFIG_SCHEMA_INVALID` is permitted because it's a documented
contract, not a label. Everything about layout, panel titles, and prose belongs to the
Tier 2 formatter test for that view.

**Rejected:**
- *Allow "semantic token presence"* — this is informally where the merged suite already
  sits, but "semantic token" vs "label" isn't a boundary that holds up mechanically; it
  reproduces the same fuzziness that made D4's `integration` marker drift.

**Rule:** `TEST-017`. Still open: the merged suite (`test_config.py`, `test_catalog.py`)
asserts `"Status: valid"`, `"Config: "`, `"Config updated: ..."`, `"(bool)"`, `"Warnings:"`
— all violations of this rule with no invariant yet enforcing it (Phase 1 W1.5).

**Superseded:** Reversed by
[0002-simplify-cli-test-doctrine.md](0002-simplify-cli-test-doctrine.md) — the
published-error-code-token restriction is dropped; CLI runner tests may assert real rendered
output directly.

## D3. `exclude` on deterministic fields

**Decided:** Fix the test. Carry the expected error text per parameterized case instead
of excluding `errors` from the comparison.

**Rejected:**
- *Relax TEST-007 to allow `exclude={"errors"}` when error codes are pinned separately* —
  an invisible waiver outside the comparison asserts nothing about the waived field at
  the point a reader looks for it.

**Status:** Already implemented, ahead of this review, in commit `6ea0f3c`
("restrict assert_model_equal exclude to non-deterministic fields"). `assert_model_equal`
has no `exclude` parameter at all now; `test_load_schema_violation_returns_validation_errors`
asserts the full literal error text per case. `TEST-007` documents this as a BLOCKER.

## D4. What `integration` actually means

**Decided:** `tmp_path` file IO stays `unit`. `integration` is reserved for subprocess
git, on-disk SQLite, and cross-process locks.

**Rejected:**
- *Widen `integration` to "touches the filesystem at all"* — deletes the documented
  execution-time budget distinction between the two tiers instead of restoring it.

**Rule:** `TEST-016`, explicit: "Writing JSON under `tmp_path` does not make a test
integration." Originally enforced since Phase 1 W1.3 by `tests/lint/test_marker_taxonomy.py`,
which allowlisted the three known-mismarked modules (`test_loader.py`, `test_mutate.py`,
`test_catalog.py`) in `INTEGRATION_MARKER_BURN_DOWN`.

**Superseded:** Reversed by
[0002-simplify-cli-test-doctrine.md](0002-simplify-cli-test-doctrine.md) — `TEST-016`'s BLOCKER
cardinality requirement is dropped and the rule no longer exists in `rules_spec.yaml`. The
passive convention check 0002 retained, `tests/lint/test_marker_taxonomy.py`, was itself
deleted once no rule referenced it, per issue #570. Marker choice is now a labeling convention
only (see `docs/agents/testing.md`), not an enforced invariant.

## D5. Fate of the TEST-007 piecewise-assertion scanner

**Decided:** Fix it, not delete it. `_scan_file_for_piecewise_result_assertions` walks
`tree.body` only, so every `*Tests`-class method in the suite is invisible to it — close
to a no-op against the suite's actual shape.

**Rejected:**
- *Delete the scanner, enforce TEST-007 as a review-time rule via `wt-review`* — the new
  `CI-004` (Mechanical Enforcement Parity) rule argues against this: a BLOCKER rule that
  can be checked mechanically must have an executing check, and TEST-007's pattern (an
  attribute access on a named result variable) is exactly that kind of mechanically
  checkable pattern. Downgrading it to review-time would need an explicit exception to
  CI-004, which nothing here justifies.

**Rule:** `CI-004`'s evaluation criteria directly names the failure: "verify invariant
checks include a regression test matching the suite's real shape, such as assertions
inside a `*Tests` class." The scanner's own regression test currently uses a top-level
`def test_func():`, which is exactly the shape CI-004 flags. Fix is still open (Phase 1
W1.2): recurse into `ClassDef` bodies, rewrite the regression test to the class shape,
land behind a `SCANNER_BURN_DOWN` allowlist populated from the first real run.

## D6. Formatter test file granularity

**Decided:** 1:1 files — one formatter, one file, at
`tests/cli/ui/formatters/<domain>/test_<name>.py`. When a formatter's transform is
provably identity, the transform test is omitted and the remaining two contracts (JSON,
Rich render) are mandatory; an alias like `SomeView = SomeEvent` must not be introduced
to manufacture a third test.

**Rejected:**
- *Allow domain-grouped mega-files* — this is what open tickets `#532`/`#533` specify
  (`test_command_formatters_part1.py` / `part2.py`, 12 and 11 formatters respectively);
  it matches neither the parity path nor the 100–250 LOC PR budget, and the one landed
  precedent (`tests/cli/ui/formatters/events/test_error_panel.py`) already follows 1:1.

**Rule:** `TEST-005`. Cites `ErrorPanelView = ErrorPanelEvent` as the negative example —
the exact alias currently in `test_error_panel.py`, which needs normalizing (Phase 2
W2.6). Tickets `#532`/`#533` need re-slicing before implementation (Phase 4 W4.2).

## D7. Coverage gate timing and shape

**Decided:** Ratchet, don't jump. Measure the real floor after Phase 2's remediation,
set `fail_under` there, raise it once per Phase 4 ticket group rather than restoring 80
in one ticket.

**Rejected:**
- *Land `#534` as specified* — it restores `fail_under = 80` and deletes `legacy_tests/`
  in the same ticket, which is exactly the "write tests to reach a percentage" failure
  mode this doctrine exists to prevent, and also destroys the only record of what the
  old suite asserted before an inventory (Phase 6) exists.

**Rule:** `CI-001`: "That floor is the contract, it ratchets upward only as real
contract tests land... a coverage drop caused by deleting duplicated or dead tests [is]
a success." `fail_under = 0` today; ticket `#534` still needs splitting (Phase 5 W5.3,
Phase 6).

## Rule IDs touched

`TEST-004`, `TEST-005`, `TEST-007`, `TEST-016`, `TEST-017`, `CI-001`, `CI-004`.

## Consequences

- `wt-review` now rejects on `TEST-004`/`TEST-005`/`TEST-016`/`TEST-017` in addition to
  the rules it already graded against, since `REVIEW_CHECKLIST.json` regenerated from
  this change.
- None of D2, D4, D5, or D6 have an executing check yet — the rule text is real but
  unenforced, which `CI-004` itself would flag if pointed at these four. That is Phase 1.
- `test_config.py`, `test_catalog.py`, and three `core` test modules are now
  known-non-compliant with rules that exist in `main`. They are the Phase 2 backlog.
