---
name: wt-test-planner
description: >-
  Given a source module (or --plan to read from an in-progress plan), produce a skeleton of test class(es) and test method stubs
  covering public observable contracts, interaction and ordering contracts, and conforming
  to this repo's tests/docs/RULES.md (TEST-001 through TEST-018). Invoked as /wt-test-planner <source-module> or
  /wt-test-planner --plan [<path>]. Use when planning, drafting, or structuring tests for a module or plan.
---

# wt-test-planner

## Purpose

Given a source module or an in-progress plan, produce a skeleton of test class(es) and test method stubs that:

- Cover every **public** symbol's observable contracts.
- Surface private-function behaviour through their public callers only.
- Produce a **balanced mix** of unit tests (fast, isolated) and integration tests (real FS,
  real subprocesses, real DB) appropriate to the module under test.
- Capture **interaction and ordering contracts** between collaborators, not just branch-by-branch
  outcomes.
- Flag every test that is parameterisable and prefer `@pytest.mark.parametrize` for sibling
  variations.
- Conform to this repo's `tests/docs/RULES.md` (TEST-001 through TEST-018).

---

## Invocation and Modes

The skill supports two data sources controlled by the `--plan` argument:

- **Existing-code mode** (default, `--plan` omitted):
  - **Invocation**: `/wt-test-planner <source-module>` (e.g. `/wt-test-planner src/worktree/core/runtime/engine.py`).
  - **Data source**: A live Python source file under `src/`.
  - **Steps 1b–1d**: Grep source code and audit existing test suites under `tests/`.
  - **Docstrings & Stubs**: Each test stub carries a mandatory single-line docstring stating the tier/type tag `[<tier>/<type>]` (per `docs/agents/testing.md#the-four-execution-tiers`), public symbol exercised, and exact contract outcome, ending with `raise NotImplementedError`.
- **Planning mode** (`--plan` provided):
  - **Invocation**: `/wt-test-planner --plan [<path>]` (defaults to `.agentic/plan.md` if `<path>` is omitted).
  - **Data source**: The in-progress plan (`.agentic/plan.md` or specified path), specifically `## Ground truth`, `## Artifact inventory`, and `## FR-<n>`.
  - **Steps 1b–1d**: Draw from the plan's Ground Truth, Traps, and Artifact inventory tables (confirming dead status traps and avoiding duplication with existing coverage).
  - **Docstrings & Stubs**: Follows `PLAN-018` and `docs/agents/planning.md` — test stubs carry the authoritative `[<tier>/<type>]` docstring contract and end with `raise NotImplementedError`.
  - **Output format**: Emits the `### Tests` summary table (`| Test | Tier | Outcome |`) paired with contract-bearing stubs, formatted to fold directly into the plan's FR sections.

### Integration with planning.md

When drafting a plan per `docs/agents/planning.md`, the skill aligns directly with the planning lifecycle:

```
planning.md Steps 1–3  →  plan: Contract + Ground Truth + Artifact inventory
skill Steps 1–5        →  plan: Ground Truth (dead status audit, Typer binding, existing coverage)
skill Steps 6–7        →  plan: Tests table + code stubs (per FR section)
planning.md Step 4     →  plan: per-FR Instructions + Code + Decisions
```

The skill's output in planning mode *is* the `### Tests` section of the plan.

---

## Step 1 — Read the governing rules and data source

Before drafting anything, read:

1. `tests/docs/RULES.md` — the full rule set (TEST-*, TYPE-*, ENCAP-*, etc.).
2. **Data source based on mode**:
   - **Existing-code mode**: The source module under analysis (e.g. `src/worktree/core/runtime/engine.py`) and any models/DTOs it returns (follow imports for `BaseResult` subtypes).
   - **Planning mode (`--plan`)**: The plan document (`.agentic/plan.md` or specified path), specifically `## Contract`, `## Ground truth`, `## Artifact inventory`, and the relevant `## FR-<n>` section.

---

## Step 1b — Trace every delegated call and audit reachable status values

For each service or facade method delegated to, **determine reachable status values**:

- **Existing-code mode**: Read the full implementation in `src/` (do not rely on docstrings alone). For each `BaseResult` subtype returned:
  1. List every value in the `status` enum.
  2. Grep the service body — and every function it calls — for assignments to each value.
  3. Mark any enum value that is **never assigned** anywhere in the reachable call chain as `DEAD`.
- **Planning mode (`--plan`)**: Read the plan's `## Ground truth` table and `Traps (explicitly not touched)`. The planner has already traced reachable status values in existing code and planned models. Use this audit to either **confirm** the plan's Traps or flag discrepancies if a planned test relies on an unassigned/dead status.

> **Rule**: Do not draft a test for a `DEAD` status value. A test that invokes
> a code path that does not exist is incorrect, not conservative.

Record your audit as a table before moving on:

```
Status value                      | Assigned in service? | Notes
----------------------------------|----------------------|------------------------------
SandboxListStatus.OK              | ✅ list.py:40        | unconditional
SandboxListStatus.NOT_INITIALIZED | ❌ never             | declared only — dead path
```

---

## Step 1c — Read the Typer binding for this command

Find the CLI binding that wraps the handler under analysis:

- **Existing-code mode**: Find the `@<app>.command(...)` function in `app.py` next to the `commands/` directory.
- **Planning mode (`--plan`)**: Read the planned Typer app/command binding from the plan's `## Ground truth` and `## Artifact inventory` tables.

Read it and record:

- **Coercions before the handler is called**: e.g. `status.value if status is
  not None else None`, Typer enum parsing, argument casting.
- **Exit behavior**: e.g. `if not result.ok: raise typer.Exit(code=1)`.
- **Options and arguments** exposed at the CLI tier that the handler never sees
  (Typer handles them entirely before calling the handler).

> **Rule**: Only draft an option-variation test when the coercion or exit
> behavior at the Typer tier adds something observable that the handler's own
> contract does not already cover. If Typer rejects an invalid enum value before
> the handler is ever called, that is Typer's contract, not yours to test.

---

## Step 1d — Check what existing tests already pin

Avoid restating contracts already pinned elsewhere:

- **Existing-code mode**: Search `tests/core/<domain>/` for tests that assert the same `BaseResult` fields the handler returns.
- **Planning mode (`--plan`)**: Read the plan's `## Ground truth` table ("Pattern to mirror" citations and existing test coverage).

The CLI tier's job is to assert **wiring**:

- Exit codes (TEST-004).
- The `--format json` wire schema as an exact literal dict (TEST-005).
- Rendered terminal tokens that come from the result (TEST-012 / TEST-017).

It is **not** the CLI tier's job to re-assert which fields the domain service
sets — that belongs in `tests/core/`.

---

## Step 2 — Identify the public surface

- **Existing-code mode**: List every symbol the module exposes that is **not** prefixed with `_`:
  ```python
  public_surface = [sym for sym in dir(module) if not sym.startswith("_")]
  ```
- **Planning mode (`--plan`)**: Extract planned public symbols from the plan's `## Artifact inventory` and `### Code` sections.

Private helpers (`_foo`, `__bar`) are **not** part of the public surface.

> **Rule**: A test class must map 1:1 to one public symbol.
> A private function never gets its own test class.

---

## Step 3 — Map private helpers to their public callers

For each private function, identify which public function(s) call it:

- **Existing-code mode**: Read the source; do not guess.
- **Planning mode (`--plan`)**: Read the planned private helpers and caller relationships from the plan's `### Instructions` and `### Code`.

Record the mapping:

```
private → public caller(s)
_parse_timestamp   → is_run_stale
_is_pid_reused     → is_run_stale
_reconcile_records → reconcile_stale_runs
```

Coverage of the private function is achieved by varying the inputs to its public
caller so each branch of the private function is exercised.

---

## Step 4 — Classify the module under test

Before drafting classes, decide which **test tiers** the module warrants. Use this
heuristic:

| Module characteristic | Tier(s) to include |
|---|---|
| Pure functions with no I/O (format strings, parsers, math) | Unit only |
| Functions that read/write the filesystem or DB | Unit + Integration |
| Functions that spawn subprocesses or drive a step-execution loop | Integration-primary, robustness unit for edge cases |
| Functions that coordinate multiple collaborators (orchestrators) | Integration for happy path, unit for error-injection edge cases |

For each tier needed, plan a **separate test class** with a descriptive suffix:

```python
class BuildDefaultConfigTests:       # unit — pure function, no I/O
class GenerateDefaultConfigTests:    # integration — real FS
class RunStepsExecutionTests:        # integration — real subprocess
class RunStepsFailurePromptTests:    # integration — real step + test-double prompter
class RunStepsPauseAndResumeTests:   # integration — checkpoint lifecycle
class RunStepsRobustnessTests:       # unit/integration mixed — error injection
```

Avoid monolithic `*Tests` classes for modules that cross tier boundaries. Splitting
by scenario group keeps fixture requirements coherent and CI parallelism effective.

---

## Step 5 — Identify interaction and ordering contracts

This is the step the branch-by-branch approach misses. After mapping branches,
**scan for sequences** where two or more private functions must cooperate in a
specific order to produce the correct observable outcome. These always become
separate test methods — they cannot be expressed as a single-function branch test.

Ask these questions about the module:

1. **Ordering**: Does function A produce a side-effect that function B must observe
   before B returns? (e.g. checkpoint saved *before* prompter is called)
2. **Lifecycle events**: Does a public function emit a sequence of observer callbacks,
   and does their order matter? (e.g. `on_sandbox_ready → on_step_start → on_step_done → on_sandbox_cleanup`)
3. **Serial vs concurrent**: Does the function guarantee sequential execution of
   sub-operations? Does the order matter to the caller?
4. **Error propagation path**: When an inner collaborator raises, does the outer
   function swallow it, wrap it, or re-raise? Each combination is a distinct contract.
5. **State preservation under partial failure**: When step N fails, is step N+1
   still attempted, and does the accumulated state (step_results, warnings) remain intact?

For each "yes" answer, add a dedicated test method whose name reflects the
**interaction** being pinned, not just a branch:

```python
# Branch test (good but insufficient on its own):
def test_pause_store_save_failure_appends_warning(self): ...


# Interaction/ordering test (adds what the branch test cannot see):
def test_checkpoint_persisted_before_prompter_is_consulted(self): ...


# Lifecycle ordering test:
def test_observer_receives_sandbox_step_and_cleanup_callbacks_in_order(self): ...


# Serial execution contract:
def test_steps_execute_strictly_serially_never_concurrently(self): ...
```

---

## Step 6 — Draft test classes and methods

### Naming (TEST-003)

Method names follow `test_<condition>_<outcome>`.
**Banned names**: `test_ok`, `test_success`, `test_basic`, `test_default`,
`test_works`, `test_missing`, `test_blank`, `test_present`, `test_timeout`,
`test_no_op`, `test_help`. No `should_` prefix.

### Mandatory Docstring with Execution Tier, Test Type, and Contract

Each method must contain a **single-line docstring** that states:

- The execution tier and test type tag: `[<tier>/<type>]` referencing `docs/agents/testing.md#the-four-execution-tiers`:
  - `[tier-1/unit]` or `[tier-1/integration]`: Tier 1 — Domain Behavior (services/facades under `core/`)
  - `[tier-2/unit]`: Tier 2 — Presentation Contracts (formatters under `cli/ui/formatters/`)
  - `[tier-3/integration]`: Tier 3 — CLI Wiring (commands under `cli/`)
  - `[tier-4/unit]`: Tier 4 — Invariants (`tests/lint/`)
- Which **public** function/command it exercises.
- Which **private** function(s) it covers indirectly (if any), and whether it is an interaction/ordering test.
- The **exact contract outcome** (exit codes, status enums, return values, or wire dicts).

```python
def test_checkpoint_persisted_before_prompter_is_consulted(self):
    """[tier-1/integration] run_steps: ordering — _try_save_checkpoint completes before failure_prompter.prompt_step_failure is called."""
    raise NotImplementedError


def test_dead_pid_returns_true(self):
    """[tier-1/unit] is_run_stale: dead pid → stale. Covers _is_pid_reused (pid not alive, skips reuse check)."""
    raise NotImplementedError
```

If a draft test's docstring would only name private symbols, the test must be
**removed or merged** into the test that covers the public caller.

### Use real execution for integration tests

Integration tests run actual shell commands or real FS operations — they do **not**
monkeypatch the function under test's internal collaborators. Inject test doubles
only at the **protocol boundary** (e.g. a `FailurePrompter`, a `RunObserver`, a
`RunPauseStore`) that the public function accepts as a parameter.

```python
# ✅ DO: inject a scripted prompter at the protocol boundary
prompter = _ScriptedFailurePrompter([FailurePromptDecision.RETRY])
context = RunContext(..., failure_prompter=prompter)
outcome = run_steps(context)

# ❌ DO NOT: monkeypatch an internal collaborator to avoid real execution
monkeypatch.setattr("worktree.core.runtime.engine._execute_one_step", fake_execute)
```

For error-injection tests where a real execution would be destructive or
unreachable (e.g. an OSError from an atomic write, a DB lock failure),
monkeypatching at the **module import boundary** is permitted, but must be noted
in the test name or plan edge cases.

### Assertion contract (TEST-001, TEST-007)

Tests assert on deliberate contracts:

- `BaseResult`/`BaseModel` subclasses: assert every field via `assert_model_equal`.
- Scalar return values: assert the exact return value.
- Observer event sequences: assert the full ordered list, not a subset.
- Serial execution: assert on a filesystem or state artifact that proves ordering
  (e.g. a log file with interleaved timestamps), not on call counts.
- Never assert call counts, constructor assignments, or private state.

### Parameterisation (TEST-006)

After drafting all methods, scan for siblings that share the **same function
under test** and the **same assertion contract** but differ only in input.
Collapse them into a single `@pytest.mark.parametrize` with explicit
`pytest.param(..., id="...")` labels.

Indicators that a test should be parameterised:

- Two or more methods in the same class with the same `_<outcome>` suffix.
- Variations of an enum value, format string, or boundary integer that feed the
  same function.
- Multiple "invalid input → None" or "missing field → default" cases.
- Multiple policy enum values that all produce the same contract shape (e.g.
  `no_tty=True` and `failure_prompter=None` both aborting with a warning).

```python
# Before (duplicate siblings — collapse these):
def test_no_tty_aborts_with_warning(self): ...
def test_no_prompter_aborts_with_warning(self): ...


# After (parameterised):
@pytest.mark.parametrize(
    ("ctx_kwargs", "warning_substr"),
    [
        pytest.param({"no_tty": True}, "non-interactive", id="no_tty"),
        pytest.param({}, "no failure prompter", id="no_prompter"),
    ],
)
def test_prompt_user_skips_prompt_and_aborts_when_non_interactive(self, ctx_kwargs, warning_substr): ...
```

Separate `def test_*` methods are reserved for **fundamentally distinct
lifecycles, fixture requirements, or divergent assertion contracts**.

---

## Step 7 — Verify compliance checklist

Run through this checklist before presenting the output:

| Check | Rule |
|---|---|
| Every test class maps to exactly one **public** symbol | TEST-002, TEST-003 |
| No test class is named after a `_private` function | TEST-001 |
| Every method has a single-line docstring with `[<tier>/<type>]` tag and exact outcome contract | PLAN-018, (this skill) |
| In planning mode (`--plan`), every test has an entry in the `### Tests` summary table | PLAN-018 |
| Any method whose docstring only names private functions has been removed or merged | (this skill) |
| At least one interaction/ordering test drafted where Step 5 produced a "yes" | (this skill) |
| Integration tests inject doubles at protocol boundaries, not internal call sites | ENCAP-002 |
| Sibling variations of the same contract are parameterised | TEST-006 |
| Method names follow `test_<condition>_<outcome>`; no banned names | TEST-003 |
| No assertion on call counts, private state, or rendered layout | TEST-001 |
| Full result objects (BaseModel) asserted with all fields named | TEST-007 |
| Test file would live at `tests/<mirror-path>/test_<module>.py` | TEST-002 |

---

## Output format

The output format matches the mode in use:

### Planning mode (`--plan`)

In planning mode, emit the `### Tests` section containing the summary table and companion stubs carrying `[<tier>/<type>]` contract docstrings, formatted to fold directly into the plan's FR sections:

````markdown
### Tests

| Test | Tier | Outcome |
|---|---|---|
| `RunStepsExecutionTests::test_two_sequential_steps_return_completed_outcome_with_both_results` | Tier 1 (integration) | steps succeed → COMPLETED, both results |
| `RunStepsExecutionTests::test_empty_step_list_returns_completed_outcome_with_no_results` | Tier 1 (integration) | steps=[] → COMPLETED, empty results |
| `RunStepsExecutionTests::test_observer_receives_lifecycle_callbacks_in_order` | Tier 1 (integration) | observer receives callbacks in order |

```python
class RunStepsExecutionTests:
    def test_two_sequential_steps_return_completed_outcome_with_both_results(self):
        """[tier-1/integration] run_steps: two steps succeed → COMPLETED, step_results contains both results with captured stdout."""
        raise NotImplementedError

    def test_empty_step_list_returns_completed_outcome_with_no_results(self):
        """[tier-1/integration] run_steps: steps=[] → COMPLETED, step_results=[], errors=[], warnings=[]."""
        raise NotImplementedError

    def test_observer_receives_lifecycle_callbacks_in_order(self):
        """[tier-1/integration] run_steps: observer receives sandbox_ready → step_start → step_done → sandbox_cleanup in that order. Interaction/ordering contract across all _notify_* helpers."""
        raise NotImplementedError
```
````

### Existing-code mode

Present the stubs as a fenced Python block. Group methods into tier-labelled
classes. Every method contains its mandatory single-line `[<tier>/<type>]` docstring. Do **not**
include import blocks or fixture bodies — stubs only.

```python
# ── Unit tests ──────────────────────────────────────────────────────────────


class IsPidAliveTests:
    def test_zero_pid_returns_false(self):
        """[tier-1/unit] is_pid_alive: pid <= 0 guard returns False without calling os.kill."""
        raise NotImplementedError

    def test_dead_pid_returns_false(self):
        """[tier-1/unit] is_pid_alive: ProcessLookupError from os.kill → process does not exist → False."""
        raise NotImplementedError

    def test_alive_pid_returns_true(self):
        """[tier-1/unit] is_pid_alive: os.kill(pid, 0) succeeds → process exists → True."""
        raise NotImplementedError

    def test_permission_error_pid_returns_true(self):
        """[tier-1/unit] is_pid_alive: PermissionError → process owned by another user but alive → True."""
        raise NotImplementedError


# ── Integration tests ────────────────────────────────────────────────────────


class RunStepsExecutionTests:
    """Happy-path and core execution contract tests using real shell commands."""

    def test_two_sequential_steps_return_completed_outcome_with_both_results(self):
        """[tier-1/integration] run_steps: two steps succeed → COMPLETED, step_results contains both results with captured stdout."""
        raise NotImplementedError

    def test_empty_step_list_returns_completed_outcome_with_no_results(self):
        """[tier-1/integration] run_steps: steps=[] → COMPLETED, step_results=[], errors=[], warnings=[]."""
        raise NotImplementedError

    def test_observer_receives_lifecycle_callbacks_in_order(self):
        """[tier-1/integration] run_steps: observer receives sandbox_ready → step_start → step_done → sandbox_cleanup in that order. Interaction/ordering contract across all _notify_* helpers."""
        raise NotImplementedError

    def test_step_output_streamed_to_observer_per_line_with_correct_stream_name(self):
        """[tier-1/integration] run_steps: stdout lines emit on_step_output with stream='stdout'; stderr lines with stream='stderr'. Covers _notify_step_output per-line streaming contract."""
        raise NotImplementedError

    def test_steps_execute_strictly_serially_never_concurrently(self):
        """[tier-1/integration] run_steps: filesystem log proves each step's end is recorded before the next step's start. Serial ordering contract across _run_remaining_steps."""
        raise NotImplementedError


class RunStepsFailurePolicyTests:
    """Failure policy branch tests using real failing shell commands."""

    def test_abort_policy_stops_run_before_later_steps(self):
        """[tier-1/integration] run_steps: step fails with on_failure=ABORT → FAILED, subsequent steps do not execute. Covers _handle_failed_step abort branch."""
        raise NotImplementedError

    def test_continue_policy_marks_step_ignored_and_runs_remaining_steps(self):
        """[tier-1/integration] run_steps: step fails with on_failure=CONTINUE → step recorded as ignored, next step runs, final status=COMPLETED. Covers _handle_failed_step continue branch."""
        raise NotImplementedError

    def test_retry_exhausted_escalates_to_on_max_retries_policy(self):
        """[tier-1/integration] run_steps: RETRY exhausted → escalates to on_max_retries policy. Covers effective_terminal_policy escalation branch."""
        raise NotImplementedError

    @pytest.mark.parametrize(
        ("ctx_kwargs", "warning_substr"),
        [
            pytest.param({"no_tty": True}, "non-interactive", id="no_tty"),
            pytest.param({}, "no failure prompter", id="no_prompter"),
        ],
    )
    def test_prompt_user_skips_prompt_and_aborts_when_non_interactive(self, ctx_kwargs, warning_substr):
        """[tier-1/integration] run_steps: prompt_user with no_tty or no prompter → abort, warning contains reason. Covers _prompt_user_decision non-interactive branches."""
        raise NotImplementedError

    @pytest.mark.parametrize(
        ("decision", "expected_status"),
        [
            pytest.param("abort", "FAILED", id="abort"),
            pytest.param("continue", "COMPLETED", id="continue"),
            pytest.param("retry", "COMPLETED", id="retry-then-succeeds"),
        ],
    )
    def test_prompt_user_decision_maps_to_correct_outcome(self, decision, expected_status):
        """[tier-1/integration] run_steps: prompter returns each FailurePromptDecision → outcome status matches. Covers _apply_prompt_decision all three branches."""
        raise NotImplementedError


class RunStepsPauseAndResumeTests:
    """Checkpoint persistence, ordering, and resume-from-checkpoint contracts."""

    def test_checkpoint_persisted_before_prompter_is_consulted(self):
        """[tier-1/integration] run_steps: ordering — _try_save_checkpoint completes before failure_prompter.prompt_step_failure is called. Interaction contract between _try_save_checkpoint and _prompt_user_decision."""
        raise NotImplementedError

    def test_pause_cleared_after_interactive_prompt_decision(self):
        """[tier-1/integration] run_steps: after prompter returns any decision, _try_clear_pause is called exactly once. Ordering contract."""
        raise NotImplementedError

    def test_no_tty_skips_checkpoint_save_and_pause_clear(self):
        """[tier-1/integration] run_steps: no_tty=True → pause_store.save_checkpoint never called, pause_store.clear_pause never called. Covers _prompt_user_decision short-circuit."""
        raise NotImplementedError

    def test_keyboard_interrupt_at_prompt_with_checkpoint_returns_paused_and_keeps_sandbox(self):
        """[tier-1/integration] run_steps: KeyboardInterrupt during prompt when checkpoint was saved → PAUSED, sandbox_kept=True. Covers PromptUserInterruptedError branch in _run_step_loop."""
        raise NotImplementedError

    def test_resume_skips_completed_steps_and_reprompts_pending_step(self):
        """[tier-1/integration] run_steps: resume_from checkpoint → already-completed step_results prepended, pending step re-prompted without re-executing. Covers _resume_pending_gate and _run_remaining_steps start-index skip."""
        raise NotImplementedError


class RunStepsRobustnessTests:
    """Observer isolation, cleanup failures, and cancellation edge cases."""

    def test_observer_exceptions_do_not_abort_run(self):
        """[tier-1/integration] run_steps: observer raises on every hook → exceptions swallowed, run completes normally. Covers all _notify_* exception-suppression branches."""
        raise NotImplementedError

    def test_keyboard_interrupt_during_step_cancels_run(self):
        """[tier-1/integration] run_steps: KeyboardInterrupt raised during step → CANCELLED, errors=['Execution cancelled by user.']. Covers _run_step_loop KeyboardInterrupt branch."""
        raise NotImplementedError

    def test_sandbox_cleanup_exception_does_not_propagate(self):
        """[tier-1/integration] run_steps: Sandbox.cleanup raises → exception swallowed, RunOutcome still returned. Covers _cleanup_sandbox best-effort branch. Monkeypatches Sandbox.cleanup at class boundary."""
        raise NotImplementedError

    def test_pause_store_save_failure_appends_warning_run_continues(self):
        """[tier-1/unit] run_steps: pause_store.save_checkpoint raises → warning appended, _try_save_checkpoint returns False, run not aborted. Covers _try_save_checkpoint exception branch. Monkeypatches pause_store."""
        raise NotImplementedError

    def test_auto_apply_conflict_marks_run_failed_and_keeps_sandbox(self):
        """[tier-1/integration] run_steps: auto_apply=True, Sandbox.apply returns conflict → FAILED, apply errors in outcome.errors, sandbox_kept=True. Covers _handle_auto_apply failed branch."""
        raise NotImplementedError
```
