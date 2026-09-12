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
- **Requirement:** Before anything else, clear the previous cycle's artifacts so a stale review or plan can never be read as current: mkdir -p .agentic && rm -f .agentic/plan.md .agentic/review.md .agentic/review.json.
- **Deliverable Contract:** Stale review and plan files removed prior to writing the new plan.
- **Validation Check:** Check that .agentic/review.md and .agentic/review.json do not exist when a new plan is generated.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
mkdir -p .agentic && rm -f .agentic/plan.md .agentic/review.md .agentic/review.json

<!-- ❌ NEGATIVE EXAMPLE -->
# Leaving previous round's .agentic/review.md in place while writing new plan
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

## [PLAN-009] Complete Artifact Inventory
- **Phase:** `Artifact Inventory`
- **Scope:** `## Artifact inventory section in .agentic/plan.md`
- **Requirement:** Produce an inventory with one row per file touched: | Artifact | Kind | Path | New or changed | Requirement |. No row may say 'e.g.' or 'etc.'. Walk the Step 3 checklist and write 'none' explicitly for untouched kinds.
- **Deliverable Contract:** Markdown table of all touched artifacts followed by 'Not needed for this issue: <kinds>'.
- **Validation Check:** Check that every touched file maps to a requirement and every unused artifact kind is listed under 'Not needed'.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
## Artifact inventory
| Artifact | Kind | Path | New or changed | Requirement |
| `SandboxPruneResult` | DTO | `src/worktree/core/sandbox/models.py` | new | FR-2 |
| `prune_command` | Command | `src/worktree/cli/sandbox/commands/prune.py` | new | FR-1 |

Not needed for this issue: DB migration, JSON/YAML schema, Config key.

<!-- ❌ NEGATIVE EXAMPLE -->
| Artifacts | Path |
| Various files in cli/ | src/worktree/cli/ |
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
- **Requirement:** Write real signature, real docstring, and numbered pseudo-code steps in comments ending with `raise NotImplementedError` for imperative bodies. Do not write finished implementation bodies in the plan.
- **Deliverable Contract:** Function stubs with signatures, docstrings, numbered steps in comments, and `raise NotImplementedError`.
- **Validation Check:** Ensure imperative methods in the plan end with `raise NotImplementedError` and are not fully implemented.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
```python
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
```

<!-- ❌ NEGATIVE EXAMPLE -->
```python
# Plan writes 40 lines of working implementation code inside the plan
def prune_sandboxes(db, cwd):
    for p in cwd.glob(...):
        shutil.rmtree(p)
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

## [PLAN-013] Multi-Tier Test Specification
- **Phase:** `Test Strategy`
- **Scope:** `### Tests section in .agentic/plan.md`
- **Requirement:** For every planned test, state the test name, execution tier (Tier 1 Domain, Tier 2 Presentation, Tier 3 CLI Wiring, Tier 4 Invariants), exact file path, and the EXACT contract asserted (exact JSON dict, exit code, BaseResult comparison). Never say 'Assert it works'.
- **Deliverable Contract:** Markdown table: | Test | Tier | Path | Exact assertion |.
- **Validation Check:** Check that every test row has an exact assertion contract and designated tier.

```markdown
<!-- ✅ POSITIVE EXAMPLE -->
### Tests
| Test | Tier | Path | Exact assertion |
| `test_prune_empty_returns_nothing_to_prune` | Tier 1 | `tests/core/sandbox/services/test_prune.py` | `result.status == SandboxPruneStatus.NOTHING_TO_PRUNE and result.pruned_items == []` |
| `test_prune_cli_exit_zero` | Tier 3 | `tests/cli/sandbox/test_prune_command.py` | `runner.invoke() exit code == 0 and json payload matches expected dict` |

<!-- ❌ NEGATIVE EXAMPLE -->
| Test | Path |
| Test pruning | tests/test_prune.py |
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
