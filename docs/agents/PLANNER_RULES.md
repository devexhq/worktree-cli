<!-- AUTO-GENERATED FROM rules_spec.yaml. DO NOT EDIT DIRECTLY. -->
# Planning Invariants & Specification Rules

> **Notice for Agents:** Plans failing `deliverable_contract` or `validation_check` will be rejected.

## [PLAN-001] Read-Only Planning Discipline
- **Phase:** `Reset & Prereqs`
- **Scope:** `Agent session & filesystem`
- **Requirement:** While planning, the agent is strictly read-only. Never edit src/ or tests/, never run tests or tooling (inv test, pytest, ruff, basedpyright, inv complexity), and never commit, push, or touch PR state. Read-only git and gh commands are the only commands permitted.
- **Deliverable Contract:** No source files edited. The plan document in .agentic/plan.md is the entire deliverable.
- **Validation Check:** Verify git status after planning shows only .agentic/plan.md created.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
# Agent reads files and gh issues, then writes only to .agentic/plan.md

<!-- ❌ NEGATIVE EXAMPLE -->
# Agent runs `inv test` or edits `src/worktree/cli/app.py` while planning
```

## [PLAN-002] Workspace Reset and State Isolation
- **Phase:** `Reset & Prereqs`
- **Scope:** `.agentic/ directory`
- **Requirement:** Before anything else, clear the previous cycle's artifacts so a stale review, plan, or master plan can never be read as current: `rm -rf .agentic && mkdir -p .agentic`. Use -rf and remove the directory itself; `rm -f` on a directory exits non-zero and short-circuits the chained mkdir, leaving every stale artifact in place while appearing to have reset. Per-file removal is insufficient because it leaves master-plan.md behind.
- **Deliverable Contract:** An empty .agentic/ directory prior to writing the new plan.
- **Validation Check:** Check that .agentic/ contains no plan.md, master-plan.md, review.md, or review.json when a new plan is generated.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
rm -rf .agentic && mkdir -p .agentic

<!-- ❌ NEGATIVE EXAMPLE -->
rm -f .agentic && mkdir -p .agentic  # fails on a directory, mkdir never runs, nothing is cleared
```

## [PLAN-003] Verbatim Contract Extraction
- **Phase:** `Contract Extraction`
- **Scope:** `## Contract section in .agentic/plan.md`
- **Requirement:** Extract the contract from the issue body without summarizing. Copy every FR-* and NFR-* verbatim with its ID. Paraphrasing requirements is strictly prohibited.
- **Deliverable Contract:** Section '## Contract' containing exact FR/NFR IDs and verbatim requirement text.
- **Validation Check:** Diff issue text against plan contract section. Flag any dropped clause or paraphrase.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
## Contract
- **FR-1**: Add `wt sandbox prune` command to remove unreferenced sandboxes.
- **FR-2**: Prune operation must delete worktree branches matching `worktree/sandbox-*`.

<!-- ❌ NEGATIVE EXAMPLE -->
## Contract
We will implement sandbox pruning for stale directories.
```

## [PLAN-004] Normative Pre-Determined Data Preservation
- **Phase:** `Contract Extraction`
- **Scope:** `## Contract section in .agentic/plan.md`
- **Requirement:** Copy Pre-determined data exactly from the issue. Field names, types, defaults, file paths, constants, error codes, and template bodies stated there are normative. You may not invent, rename, or 'improve' them.
- **Deliverable Contract:** Pre-determined data reproduced identically under '## Contract'.
- **Validation Check:** Verify all field names, types, and defaults in code samples match the issue's Pre-determined data.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
### Pre-determined data
- Model: `SandboxPruneResult`
- Field: `pruned_items: list[str] = []`
- Exit code on error: `1`

<!-- ❌ NEGATIVE EXAMPLE -->
# Plan renames `pruned_items` to `deleted_sandboxes` because it sounds "better"
```

## [PLAN-005] Out-of-Scope Guardrails
- **Phase:** `Contract Extraction`
- **Scope:** `### Out of scope section in .agentic/plan.md`
- **Requirement:** Copy Out of scope verbatim from the issue into the plan's guardrail section. Treat it as a strict stop sign, not a hint.
- **Deliverable Contract:** Subsection '### Out of scope (verbatim from the issue)' containing exact bullet points.
- **Validation Check:** Verify that all items marked out of scope are explicitly listed and omitted from artifact inventory.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
### Out of scope (verbatim from the issue)
- Interactive confirmation prompt before pruning
- Pruning sandboxes on remote git repositories

<!-- ❌ NEGATIVE EXAMPLE -->
# Omitting Out of scope section or planning an interactive confirmation prompt
```

## [PLAN-006] Greenfield Architecture Default
- **Phase:** `Contract Extraction`
- **Scope:** `Entire plan`
- **Requirement:** Plan zero compatibility shims, aliases, dual code paths, or deprecation windows unless the issue explicitly states a compatibility constraint. Plan to replace superseded paths and update callers in the same change set.
- **Deliverable Contract:** Direct replacements planned; zero shims or legacy fallback adapters in artifact inventory.
- **Validation Check:** Check artifact inventory for compatibility wrappers or fallback flags.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
# Plan directly replaces SandboxService.delete() with unified lifecycle pruner

<!-- ❌ NEGATIVE EXAMPLE -->
# Plan introduces `LegacySandboxService` and adds deprecation warning shims
```

## [PLAN-007] Tree Grounding and Neighbor Mirroring
- **Phase:** `Grounding & Traps`
- **Scope:** `## Current state section in .agentic/plan.md`
- **Requirement:** Never plan from memory. Read always-on docs, inspect live domain source files, and name the closest existing implementation you will mirror with exact file:line citations.
- **Deliverable Contract:** Ground-truth table with columns | Surface | Location | What exists today |, plus explicit 'Pattern to mirror: <path:line>'.
- **Validation Check:** Verify cited file:line citations exist in the live codebase and match cited functionality.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
## Current state
| Surface | Location | What exists today |
| CLI app | `src/worktree/cli/sandbox/app.py:24` | Typer app registering sandbox subcommands |
| Lifecycle | `src/worktree/core/sandbox/services/lifecycle.py:80` | `delete_sandbox` method |

**Pattern to mirror:** `src/worktree/cli/config/commands/config_set.py:30`

<!-- ❌ NEGATIVE EXAMPLE -->
# Plan designs new command from scratch without citing existing neighbor commands
```

## [PLAN-008] Trap Identification and Isolation
- **Phase:** `Grounding & Traps`
- **Scope:** `## Current state section in .agentic/plan.md`
- **Requirement:** Explicitly name every trap a lower-context implementer could fall into: dead code, similarly-named-but-unrelated symbols, duplicate implementations, or stale docs. Mark each explicitly out of scope.
- **Deliverable Contract:** Subsection '**Traps (explicitly not touched):**' naming specific symbols and paths.
- **Validation Check:** Verify known hazards (e.g. core/runtime/engine.py vs core/engine/engine.py) are trapped when touched.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
**Traps (explicitly not touched):**
- `core/runtime/engine.py`: Do not import Engine from here (that is `run_steps`). Engine lives in `core/engine/engine.py`.
- Stale doc claim in `schemas.md` §4 mentioning `renderers.py`: Do not create `renderers.py`.

<!-- ❌ NEGATIVE EXAMPLE -->
# Plan fails to warn implementer about known naming collision or dead code
```

## [PLAN-009] Complete Artifact Inventory and Deletion Ledger
- **Phase:** `Artifact Inventory`
- **Scope:** `## Artifact inventory section in .agentic/plan.md`
- **Requirement:** Produce an inventory with one row per file touched: | Artifact | Kind | Path | New or changed | Requirement |. No row may say 'e.g.' or 'etc.'. Walk the artifact checklist and write 'none' explicitly for untouched kinds. Follow it with a deletion ledger, one row per removal: | Path or symbol | Why it goes | Replaced by |, covering superseded code paths (COMPAT-002), tests that duplicate a contract asserted elsewhere (TEST-004), and harness symbols whose only caller would be their own verification test (TEST-013). A change that deletes nothing states 'Deletes nothing: greenfield' explicitly, so the omission is a decision rather than an oversight. Deletions are executed in the same change set as the code that supersedes them, and never recorded as a negative existence test (TEST-009).
- **Deliverable Contract:** Markdown inventory table followed by 'Not needed for this issue: <kinds>', then a deletion ledger table or the explicit 'Deletes nothing: greenfield' line.
- **Validation Check:** Check that every touched file maps to a requirement, every unused artifact kind is listed under 'Not needed', and the deletion ledger is present with either rows or the explicit greenfield statement.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
## Deletion ledger
| Path or symbol | Why it goes | Replaced by |
| `tests/cli/commands/test_config.py::ConfigShowRootTests` | pass-through handler restating a domain contract | `tests/core/config/test_loader.py` |

<!-- ❌ NEGATIVE EXAMPLE -->
# Inventory lists 9 new files and says nothing about what they supersede
```

## [PLAN-010] Literal Final Code for Contracts
- **Phase:** `Specification & Samples`
- **Scope:** `### Code section in .agentic/plan.md`
- **Requirement:** Write literal, production-ready code for anything that is a contract: models with model_config, enum definitions, function/method signatures with full type hints and docstrings, Typer argument/option declarations, exact JSON dicts, and error/warning strings.
- **Deliverable Contract:** Fully typed models, signatures, and literal dictionaries in code blocks.
- **Validation Check:** Verify contract code blocks leave no ambiguous types, missing defaults, or unspecified flags.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
```python
class SandboxPruneStatus(StrEnum):
    OK = "ok"
    NOTHING_TO_PRUNE = "nothing_to_prune"
    FAILED = "failed"

class SandboxPruneResult(BaseResult):
    model_config = {"extra": "forbid", "strict": True}
    status: SandboxPruneStatus
    pruned_items: list[str] = []
```

<!-- ❌ NEGATIVE EXAMPLE -->
```python
# Plan writes vague sketch:
class SandboxPruneResult:
    # fields for status and pruned items
    pass
```
```

## [PLAN-011] Signature Plus Pseudo-Code for Imperative Bodies
- **Phase:** `Specification & Samples`
- **Scope:** `### Code section in .agentic/plan.md`
- **Requirement:** Write real signature, real docstring, and numbered pseudo-code steps in comments ending with `raise NotImplementedError` for production imperative bodies. For test method bodies, setup steps may be outlined in comments, but all assertions on results, models, or command outputs must be written as literal Python code using `assert_model_equal(...)` or whole-dictionary equality. Banned in test stubs: conversational assertions ('verify status is OK'), bare `assert result.exit_code == 0`, piecewise attribute checks, or using `exclude` in `assert_model_equal` on deterministic fields (e.g. `exclude={"errors"}`).
- **Deliverable Contract:** Production function stubs with signatures, docstrings, numbered steps in comments, and `raise NotImplementedError`. Test stubs with signatures, docstrings, setup comments, literal whole-object assertions, and `raise NotImplementedError`.
- **Validation Check:** Ensure imperative production methods end with `raise NotImplementedError` and are not fully implemented. Ensure test stubs contain literal whole-object assertions rather than loose conversational comments or lazy exclusions.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
```python
# Production stub:
def prune_sandboxes(db: SandboxesRepository, cwd: Path) -> SandboxPruneResult:
    """Prune unreferenced git worktree sandboxes.

    Args:
        db: Isolated sandboxes repository slice.
        cwd: Target workspace root directory.
    """
    # 1. Query active sandboxes from db
    # 2. Inspect on-disk sandboxes under .worktree/sandboxes/
    # 3. Delete unreferenced worktrees and git branches
    # 4. Return SandboxPruneResult with status=OK
    raise NotImplementedError

# Test stub:
def test_prune_empty_returns_nothing_to_prune(self, isolated_workspace: Path) -> None:
    """Prune returns NOTHING_TO_PRUNE when sandboxes directory is empty."""
    # 1. Build context with clean workspace
    # 2. Call prune_sandboxes
    assert_model_equal(
        result,
        SandboxPruneResult(status=SandboxPruneStatus.NOTHING_TO_PRUNE, pruned_items=[]),
    )
    raise NotImplementedError
```

<!-- ❌ NEGATIVE EXAMPLE -->
```python
# ❌ Test stub with informal comments or lazy exclude:
def test_prune(self):
    # 1. Run prune
    # 2. Assert exit_code == 0 and status is ok
    assert_model_equal(result, expected, exclude={"errors"})
    raise NotImplementedError
```
```

## [PLAN-012] Pre-Decomposed Complexity
- **Phase:** `Specification & Samples`
- **Scope:** `### Code section in .agentic/plan.md`
- **Requirement:** Decompose complex workflows into named helper functions in the plan itself so that every planned function holds cognitive complexity <= 10.
- **Deliverable Contract:** Multiple focused function signatures with single responsibilities rather than one large function.
- **Validation Check:** Verify no single planned function contains more than 3 branching levels or complex nested loops.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
def prune_stale_records(db: SandboxesRepository) -> list[str]: ...
def prune_orphaned_directories(sandboxes_dir: Path) -> list[str]: ...
def prune_sandboxes(...) -> SandboxPruneResult: ...

<!-- ❌ NEGATIVE EXAMPLE -->
# Single 80-line function planned to do querying, directory diffing, git branch deleting, and error handling
```

## [PLAN-013] Test Ledger Specification
- **Phase:** `Test Strategy`
- **Scope:** `### Tests section in .agentic/plan.md`
- **Requirement:** Specify planned tests as a ledger with one row per test file: | Path | Marker | Est. lines | Contract pinned | Nearest existing coverage | Verdict |. Path must satisfy the TEST-002 mappings, with no part-numbered or grab-bag files. Marker is the primary pytest marker (unit, integration, cli, invariant, optionally combined with slow), chosen by real execution cost, since the marker is what a filtered run selects and a prose tier label is not. Est. lines keeps the change reviewable under PLAN-017. Nearest existing coverage is the result of grepping the suite for a test already pinning that contract; when one exists the verdict is redundant-dropped and the row stays as the record of the decision. A second CLI tier is specified only where TEST-004 earns it: a pass-through handler gets no root test, and no row may restate a contract already asserted under tests/core/ for the same result type. Assertions on returned models or event payloads must specify whole-object comparison (assert_model_equal(result, ExpectedModel(...)) or assert json.loads(res.stdout) == expected_dict), never piecewise field checks, bare attribute assertions, or any waiver expressed outside the comparison; per TEST-007 the expected object names every field, and a value the test cannot own is stated as a matcher at that field's position. Assertions against panel titles, status labels, captions, prose, or glyphs in a formatter test under tests/cli/ui/formatters/ are restricted to values carried by the view model (TEST-012); a CLI runner test under tests/cli/commands/ may assert rendered output directly (TEST-017). Never say 'Assert it works'. Any test whose assertion is the absence of violations must specify a companion negative fixture test and a non-empty collection assertion (CI-004).
- **Deliverable Contract:** Markdown ledger: | Path | Marker | Est. lines | Contract pinned | Nearest existing coverage | Verdict |.
- **Validation Check:** Check that every row resolves under the TEST-002 mapping, carries exactly one primary marker, states an exact assertion contract with zero piecewise checks or lazy exclusions, records the existing-coverage search, and that every planned enforcement test names its negative fixture.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
### Test ledger
| Path | Marker | Est. lines | Contract pinned | Nearest existing coverage | Verdict |
| `tests/core/bootstrap/test_initialize.py` | `integration` | 120 | `assert_model_equal(result, InitResult(status=NOT_A_GIT_REPO, created=[]))` | none found | new |
| `tests/cli/commands/test_init.py` | `cli` | 90 | `assert json.loads(res.stdout) == expected_wire_dict` | none found | new |
| `tests/cli/commands/test_config.py::ConfigShowRootTests` | - | - | ConfigLoadResult shape | `tests/core/config/test_loader.py` | redundant-dropped |

<!-- ❌ NEGATIVE EXAMPLE -->
| Test | Tier | Path | Exact assertion |
| Test pruning | Tier 1 | tests/test_prune.py | assert_model_equal(result, Expected(...), exclude={"errors"}) |
```

## [PLAN-014] Flagging Unspecified Decisions with 🚨
- **Phase:** `Cross-Cutting & Validation`
- **Scope:** `### Decisions & ## Cross-cutting in .agentic/plan.md`
- **Requirement:** When an issue leaves a detail genuinely unspecified, do not stall or invent product behavior: choose the option consistent with nearest neighbor patterns, record the choice and rejected alternative, and append 🚨 so human reviewers catch it.
- **Deliverable Contract:** Decision bullet: - **<point>:** <choice>, because <reason>. Rejected: <alt>. 🚨.
- **Validation Check:** Verify all unspecified assumptions are flagged with 🚨 in the plan and restated in the agent handoff message.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
- **Prune branch deletion policy:** Delete local branches matching `worktree/sandbox-*` automatically, because active sandboxes track branches 1:1. Rejected: prompt user for each branch. 🚨

<!-- ❌ NEGATIVE EXAMPLE -->
# Silent design choice made without recording alternative or flagging with 🚨
```

## [PLAN-015] Plan Target Path and Human Handoff Protocol
- **Phase:** `Self-Check & Handoff`
- **Scope:** `Deliverable file & Chat response`
- **Requirement:** Write the plan to .agentic/plan.md. Run the 9-item self-check before handing off. In chat, report the path, a one-paragraph summary, all 🚨 decisions and open questions, and state plainly that this was planning only: nothing was implemented, tested, committed, or pushed. Stop and wait for human review.
- **Deliverable Contract:** File written to .agentic/plan.md. Agent turn terminates without executing implementation commands.
- **Validation Check:** Ensure the agent does not immediately proceed to invoke /wt-code or edit production files.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
"Plan saved to .agentic/plan.md. Planning only; nothing was implemented or committed.
Open decisions requiring confirmation:
- 🚨 Prune branch deletion policy: auto-delete worktree/sandbox-* branches."

<!-- ❌ NEGATIVE EXAMPLE -->
"Plan written. Now I will start writing the code..."
```

## [PLAN-016] Item-by-Item Checklist Compliance Audit
- **Phase:** `Pre-Handoff Self-Audit`
- **Scope:** `## Architectural Context & Boundary Check in .agentic/plan.md`
- **Requirement:** Before finalizing .agentic/plan.md, sweep docs/agents/REVIEW_CHECKLIST.json item by item for all rules matching touched paths or domains, and record each in a required '### Rule Evaluation Matrix' table with columns | Rule ID | Clause | Severity | Status | Evidence (quoted) |. Four requirements make the sweep real. First, decompose a multi-clause rule into one row per clause: TEST-007 carries three (whole-object comparison, exclude restricted to non-deterministic fields, separate presence assertions for excluded fields), and a single row hides two of them. Second, status is PASS, FAIL, or N/A; FAIL is a permitted and expected interim value, and every FAIL is resolved in the plan before saving, so the saved plan carries zero. A matrix that can only say PASS or N/A audits nothing. Third, evidence quotes the plan's own stub or section verbatim; restating the rule is not evidence, and the phrases 'follows the pattern', 'complies', 'contract-based', and 'uses assert_model_equal' are prohibited because they read identically against a violating plan. N/A names why the scope does not match. Fourth, for every BLOCKER clause, write the one sentence a reviewer would use to fail the plan, then either fix the plan or record why the sentence does not hold; a self-audit with no adversarial step approves itself.
- **Deliverable Contract:** Required '### Rule Evaluation Matrix' subsection covering every matching rule clause with PASS, FAIL, or N/A status and quoted evidence, zero FAIL rows remaining at save time, plus the adversarial sentence for each BLOCKER clause.
- **Validation Check:** Verify the matrix covers all matching rules clause by clause, that each PASS quotes a literal line from the plan rather than paraphrasing the rule, that no FAIL row remains, and that each BLOCKER clause carries its adversarial sentence.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
### Rule Evaluation Matrix
| Rule ID | Clause | Severity | Status | Evidence (quoted) |
| `TEST-007` | exclude restricted to non-deterministic fields | BLOCKER | FAIL -> fixed | Phase 4 stub read `assert_model_equal(result, expected, exclude={"errors"})`; rewritten to carry expected errors per parameter case |
| `TEST-002` | path mirrors source module | BLOCKER | PASS | Ledger row 3 is `tests/cli/ui/formatters/status/test_status.py` for `cli/ui/formatters/status/status.py` |

<!-- ❌ NEGATIVE EXAMPLE -->
| `TEST-007` | Whole Object Comparison | BLOCKER | PASS | Uses assert_model_equal on whole ConfigLoadResult |
```

## [PLAN-017] Test Ticket Scope Contract
- **Phase:** `Test Strategy`
- **Scope:** `Any issue whose deliverable is test files`
- **Requirement:** A ticket delivering tests must declare, before implementation, the exact test file paths conforming to the TEST-002 mappings, the primary marker for each module, a line budget inside the 100 to 250 range with a split plan when the estimate exceeds it, and the rule IDs the work is graded against. Scope stated as a list of test method names without paths and markers is not a specification.
- **Deliverable Contract:** The In scope section lists one bullet per test file as path, marker, and estimated lines, followed by the contracts asserted in that file. The Definition of Done cites the rule IDs and names the formatter test or domain test that owns any behavior deliberately not covered here.
- **Validation Check:** Every declared path resolves under the TEST-002 mapping for its source module, every module has exactly one primary marker, and the summed line estimate stays within budget or carries a split plan.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
### In scope
- `tests/core/bootstrap/test_initialize.py` (integration, ~120 lines): preflight failure modes,
  zero-side-effect abort, idempotent rerun
- `tests/cli/commands/test_init.py` (cli, ~90 lines): runner exit codes, `--format json` payload, `--force`

### Rules
TEST-002, TEST-004, TEST-017

<!-- ❌ NEGATIVE EXAMPLE -->
### In scope
- Create tests for init covering the happy path and some failure cases
- Add CLI tests for every action with RootTests and CliIntegrationTests
```
