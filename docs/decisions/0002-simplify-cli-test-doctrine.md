# 0002. Simplify CLI test doctrine: reverse D1, D2, D4 from ADR-0001

- Status: Accepted
- Date: 2026-09-16
- Driven by: GitHub issue #569 ("Relax dual-tier CLI, marker-taxonomy, and output-label doctrine
  in rules_spec.yaml"), citing a comparison against copier's `AGENTS.md` test doctrine.

## Context

[0001-test-doctrine-phase-0.md](0001-test-doctrine-phase-0.md) made seven decisions (D1-D7) after
the 09-16 review found doctrine and merged tests disagreeing. Landing D1 (dual-tier CLI), D2 (CLI
runner assertion boundary), and D4 (marker taxonomy fidelity) as BLOCKER, mechanically-enforced
rules bought little: worktree-cli is a copier-scale project, and copier's own `AGENTS.md` gets
equivalent coverage from single real-invocation CLI/formatter tests with no paired root-test
mandate, no four-way marker taxonomy, and no token-vs-label output distinction. The enforcement
cost — a `*RootTests` suite required by convention rather than earned by logic, a
marker-cardinality invariant test carrying two burn-down allowlists, a CLI-runner assertion
boundary that forced an error-code token instead of pinning real rendered output — exceeded the
drift risk those three rules were bought to prevent.

D3 (`exclude` ban), D5 (TEST-007 scanner fix), and D7 (coverage ratchet) are unaffected: none of
them are assertion-style or tiering rules, and D3/D5's status in ADR-0001 was already "implemented"
/ "fix landed," not open doctrine debate.

D6 (formatter test file granularity, `TEST-005`) and `TEST-002` (1:1 source parity) were
considered for the same reversal and rejected: worktree-cli deliberately keeps `core/config`,
`core/sandbox`, `cli/ui/formatters/<domain>`, etc. as real, separately-owned modules, unlike
copier's flat, monolithic source (a handful of god files like `_main.py`). The 1:1 test-to-module
mapping these two rules encode is a structural fact about worktree-cli's own architecture, not a
testing-philosophy import from the copier comparison, so it does not transfer.

## D1 reversal: dual-tier CLI mandate (TEST-004)

**Was:** `*CliIntegrationTests` mandatory per command action; `*RootTests` required only when the
handler owns logic the domain layer does not.

**Now:** A `*RootTests` suite is optional, earned only when an author judges the handler's own
logic worth isolating. A pass-through handler is fully compliant with zero root tests. The
`*CliIntegrationTests` requirement (one real `CliRunner` invocation per action, covering the four
scenarios, plus the ban on a root test restating a `tests/core/` contract) is unchanged.

**Rejected:** Drop the four-scenario `*CliIntegrationTests` matrix too. Issue #569's FR-1 only
asks to drop the root-test mandate; the four-scenario coverage isn't named as relaxed, so it
stays. 🚨

## D2 reversal: CLI runner assertion boundary (TEST-017)

**Was:** CLI runner tests could assert a published error-code token only; every other rendered
string (panel titles, status labels, captions, prose) was Blocking and had to move to the
formatter test.

**Now:** CLI runner tests may assert real rendered output directly — a label, a token, a full
string — ideally pinned via snapshot testing. The only remaining prohibition is help-text
wording, which still routes through Click metadata assertions. `TEST-012`'s formatter-render rule
(semantic-value-only assertions in `tests/cli/ui/formatters/`) is untouched: this reversal only
widens what `tests/cli/commands/` tests may assert, not what formatter tests may assert.

**Rejected:** Also relax `TEST-012` so formatter tests could assert captions/labels directly.
Issue #569 explicitly scopes this ticket to `TEST-004`, `TEST-016`, `TEST-017` only; `TEST-012`
stays untouched.

🚨 **Doctrine defect this reversal surfaces:** issue #569's own "Add ADR-0002" bullet names only
D1 and D4 for reversal, not D2, even though its FR-3 amends `TEST-017` (D2's rule). Read as an
omission rather than an intentional exclusion, since D2 isn't listed among the "D3/D5/D7 stand
unchanged" set either. This ADR records D2 as reversed to keep the decision log accurate.

## D4 reversal: marker taxonomy fidelity (TEST-016)

**Was:** Every test module resolves to exactly one primary marker (BLOCKER), mechanically
enforced by `tests/lint/test_marker_taxonomy.py` with two burn-down allowlists
(`INTEGRATION_MARKER_BURN_DOWN`, `PRIMARY_MARKER_BURN_DOWN`) and one permanent exemption list
(`INTEGRATION_HEURISTIC_EXEMPT`).

**Now:** `TEST-016` is dropped entirely from `rules_spec.yaml`, not merely downgraded — it is no
longer a BLOCKER, or any severity, rule. 🚨 **Deviation from the plan's original deletion ledger:**
the plan called for deleting `tests/lint/test_marker_taxonomy.py` alongside the rule, on the
reasoning that a passing invariant test enforcing a retired mandate reproduces the enforcement
cost this reversal exists to remove. The implementer of this reversal was instructed not to
delete any test file. `tests/lint/test_marker_taxonomy.py` is therefore **retained as-is**: it
keeps running under `pytest -m invariant` and keeps checking the same shape (exactly one primary
marker per module, `invariant` confined to `tests/lint/`), but a failure it reports is no longer
backed by a `rules_spec.yaml` BLOCKER and is not grounds for a `wt-review` rejection. The five
registered pytest markers (`unit`, `integration`, `cli`, `invariant`, `slow`, in `pyproject.toml`)
and `docs/agents/testing.md`'s marker vocabulary table remain: they are still a useful filtering
convention (`pytest -m unit`, etc.), just no longer a BLOCKER cardinality requirement, and now
also checked by a file with no rule ID behind it.

**Rejected:** Downgrade `TEST-016` to WARNING instead of deleting the rule. Issue #569's own
in-scope bullet says "drop the rule," not "downgrade," and the rule itself carries no enforcement
value once nothing in `rules_spec.yaml` cites it.

🚨 **Collateral edits this reversal forces**, none named in issue #569's "Files Changed" list, all
required so the repository stops asserting an enforcement that no longer exists (`DOC-008`):
- `docs/agents/rules_spec.yaml`'s `CI-004` guideline text ("CI must exercise the marker taxonomy
  so the tiers have a consumer and cannot drift.") and its `positive_example`
  (`# TEST-016 enforced by tests/lint/test_marker_taxonomy.py plus a CI job per marker`) both name
  the dropped rule. The example is repointed at `TEST-007`/`tests/lint/test_assertion_style.py`,
  a still-live, still-enforced pairing.
- `docs/agents/rules_spec.yaml`'s `planner_rules` entries `PLAN-013` and `PLAN-017` cite
  `TEST-016` by name in their `requirement` prose and in `PLAN-017`'s `positive_example` rule
  list.
- `PLAN-013`'s `requirement` also described `TEST-017`'s pre-reversal prohibition ("panel titles,
  status labels, captions, prose, or glyphs... prohibited at any tier") as still binding; reworded
  to scope that prohibition to formatter tests (`TEST-012`) and note the CLI-runner tier now
  permits direct rendered-output assertions (`TEST-017`).
- `.agents/skills/wt-code/SKILL.md`, `.agents/skills/wt-plan/SKILL.md`,
  `.agents/skills/wt-review/SKILL.md` all cite `TEST-016` and describe the pre-reversal
  `TEST-004`/`TEST-017` behavior in their operating instructions and rule-provenance tables —
  `DOC-008`'s scope explicitly includes `.agents/skills/`. Commit `6d0d2bc` ("docs: Update skills
  to align with rule changes") is direct precedent for keeping these three files synchronized
  with `rules_spec.yaml`.

## D6, TEST-002, and TEST-005 considered and rejected for reversal

**Rejected:** Extend this reversal to `TEST-002` (1:1 source parity) or `TEST-005` (1:1 formatter
file granularity), matching copier's flatter test layout. Copier's tests are flat because
copier's source is flat (a handful of god files). Worktree-cli deliberately keeps `core/config`,
`core/sandbox`, `cli/ui/formatters/<domain>`, etc. as real, separately-owned modules; the 1:1
test-to-module mapping these two rules encode is structure-dependent, not a testing-philosophy
choice, and doesn't transfer from the copier comparison. Both rules stay `BLOCKER`, unmodified
(issue #569 FR-5).

## Rule IDs touched

`TEST-004`, `TEST-016` (removed), `TEST-017`, and `CI-004` (guideline/example correction only,
not a policy reversal).

## Consequences

- `wt-review` no longer rejects a CLI command action for missing a `*RootTests` suite, nor a CLI
  runner test for asserting a literal rendered string beyond a published error-code token, nor a
  test module for an absent or multiple primary marker.
- `tests/lint/test_marker_taxonomy.py` and its two burn-down allowlists remain in the tree,
  unlinked from any rule; the three real mismarked modules it tracks (`test_loader.py`,
  `test_mutate.py`, `test_catalog.py`) are still flagged by the test itself but are no longer a
  BLOCKER per `rules_spec.yaml`. A future ticket may delete the file outright to finish what this
  reversal started, or re-point it at a new, lower-severity rule; neither is decided here.
- `docs/agents/testing.md`, `docs/agents/rules_spec.yaml`'s `planner_rules`, and the three
  `.agents/skills/*.md` files needed edits beyond `TEST-004`/`TEST-016`/`TEST-017`'s own rule
  blocks to stop citing a dropped rule or describing pre-reversal behavior as current.
