# Testing

Testing conventions, taxonomy, harness utilities, and execution patterns for Worktree CLI.
Architectural reference: `scratch/test-structure-proposal.md`.

---

## The rule that matters most

**Test at contracts, not at implementation.** A contract is a boundary we chose deliberately: a `BaseResult` object, a JSON payload, an exit code, a file on disk, a git ref. Implementation is everything else: rendered layout, private helpers, call ordering, constructor assignments.

Asserting on implementation costs brittleness and buys no safety. A suite can reach 90% line coverage while missing every real defect, and this one has.

---

## 1:1 Source Parity Layout

Test structure mirrors `src/worktree/` 1:1 under `tests/`. **A test lives beside what it tests.** If a module moves package, its test moves in the same commit.

- Every source module in `src/worktree/` has exactly one corresponding test file in `tests/`:
  - `src/worktree/core/<domain>/<module>.py` -> `tests/core/<domain>/test_<module>.py`
  - `src/worktree/cli/<command>/commands/<action>.py` -> `tests/cli/<command>/test_<action>_command.py`
  - `src/worktree/cli/ui/formatters/<domain>/<name>.py` -> `tests/cli/ui/formatters/<domain>/test_<name>.py`
- Every test directory gets an `__init__.py`. Basenames repeat across the tree (`test_formatters.py`, `test_filesystem.py`), so collection depends on packages being real.
- **One test file per source module.** Do not split one module's tests across files without a stated architectural rule.
- **Import boundaries in tests:** `tests/core/**` must never import `worktree.cli.*`.

---

## Naming Conventions

### Test Class Naming

- **Pick one class-naming convention: `*Tests`.** `pyproject.toml` sets `python_classes = ["Test*", "*Tests"]`, so both collect. Standardize on `*Tests` (e.g. `ConfigLoaderTests`, `DiffCommandRootTests`).
- Standalone `test_*` functions are preferred over test classes when grouping by class provides no fixture reuse or parameterized setup benefit.

### Test Method Naming

**`test_<condition>_<outcome>`.** The class or module carries the subject; the method carries what varies and what results. A reader must get the behavior from the node id alone, which is what a failure prints:
`ResolveApiKeyTests::test_returns_key_when_set` says what `test_present` hides.

| Opaque | Same test, decipherable |
|---|---|
| `test_present` | `test_returns_key_when_set` |
| `test_timeout` | `test_timeout_maps_to_error` |
| `test_success_block` | `test_create_ok_includes_sandbox_id` |
| `test_no_op` | `test_no_edits_leaves_tree_unchanged` |

**Banned: a name with no outcome.** `test_ok`, `test_success`, `test_present`, `test_missing`, `test_blank`, `test_basic`, `test_default`, `test_works`, `test_timeout`, `test_no_op`, `test_help`. A `should` prefix is not an outcome: `test_should_present` is `test_present` with filler, so do not add one.

**Docstrings are optional, and must not restate the name.** `tests/*` ignores Ruff's `D` rules deliberately. Write one only for a constraint an identifier cannot carry: "detached grandchild processes are killed when step times out" earns it; "Verify collect without config raises ConfigLoadError" above `test_collect_no_config_raises_on_missing_config` does not. If swapping the docstring for the name would not change a reader's understanding, delete it.

---

## Pytest Marker Taxonomy & Module-Level Tagging

All tests must be categorized under one of the five registered markers declared in `pyproject.toml`:

| Marker | Scope and Criteria | Execution Limit | Invocations & Usage |
|---|---|---|---|
| `unit` | Fast in-memory tests without subprocesses, disk SQLite, or real Git commands. Pure logic, mocked clocks, or pure objects. | < 5ms per test | `pytest -m unit` (sub-second local dev loop) |
| `integration` | Subsystem boundary tests: real Git worktrees, SQLite disk transactions, file locks, and filesystem mutations. | < 500ms per test | `pytest -m integration` |
| `cli` | Typer CLI command routing, option parsing, Click argument binding, and dispatcher output tests. | Fast / runner-scoped | `pytest -m cli` (verifies CLI flag wiring) |
| `invariant` | Static AST and architectural boundary enforcement tests (`tests/lint/`). Verifies imports, complexity, and contract consistency. | Fast / AST scan | `pytest -m invariant` (instant architecture guard) |
| `slow` | Long-running tests involving process group signal escalation, real process timeouts, cross-process locks, or network boundaries. | > 500ms | `pytest -m "not slow"` (runs suite excluding slow waits) |

### Module-Level Tagging Pattern (Optional)

Test modules may declare markers at module top level using `pytestmark` immediately below the imports:

```python
import pytest

pytestmark = pytest.mark.unit
```

For modules combining multiple characteristics (e.g. integration tests with long timeouts):

```python
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]
```

### CLI Execution Recipes

Filter test runs with the registered markers:

```bash
uv run pytest -m unit                 # Fast in-memory test suite only
uv run pytest -m integration          # Subsystem boundary tests
uv run pytest -m cli                  # CLI routing and runner tests
uv run pytest -m invariant            # Lint and architectural AST invariants
uv run pytest -m "not slow"           # All tests excluding long-running/timeouts
uv run pytest -m "unit or cli"        # Fast pre-commit test cycle
inv test                              # Full suite via xdist parallel execution
```

---

## The Four Execution Tiers

Different subject, different mocking policy, different assertion style. Do not mix them in one test.

### Tier 1 - Domain Behavior (Most Tests)

- **Subject:** Services and facades under `core/`.
- **Assert on:** Returned `BaseResult` objects (status, errors, warnings, fixes) and real side effects (files written, git refs created, DB rows committed).
- **Mocks:** None, except genuine process boundaries or network APIs. Use real `tmp_path` filesystems, SQLite databases, and `GitWorkspaceHarness`.
- **Marker:** `unit` for pure domain logic; `integration` when touching real Git worktrees or disk SQLite.

### Tier 2 - Presentation Contracts (Three Tests Per Formatter, Never One)

Every formatter under `src/worktree/cli/ui/formatters/<domain>/` must have three tests in `tests/cli/ui/formatters/<domain>/test_<name>.py`:

1. **View model transformation:** assert `transform(model) == ExpectedView(...)` to pin the typed intermediate presentation model and verify all derivations.
2. **JSON wire format:** assert `to_json_serializable(model)` as an **exact literal dict** (pinned at boundary states: fully populated and empty/sparse). Never assert `== transform(model).model_dump(...)`, because only a literal dict pins field names, enum spellings, and null-versus-absent serialization.
3. **Rich renderable:** render at a pinned width (`render_rich(...)`) and assert **only values that came from the view model** (ids, names, counts, error text). Read expectations directly from `case.view` so Rich assertions cannot drift from the transform test. Never assert a label, border, glyph, padding, or a full sentence.

#### Canonical Tier 2 Test Structure

Tier 2 tests use `tests.harness.formatter.FormatterCase` (or `tests.harness.FormatterCase`) to define presentation scenarios once, feeding three focused test functions:

```python
from pathlib import Path
from typing import Any
import pytest
from tests.harness.formatter import FormatterCase, render_rich
from worktree.cli.ui.formatters.status import WorktreeStatusFormatter
from worktree.cli.ui.formatters.status.status_view import StatusHealth, StatusView
from worktree.core.status.models import (
    CatalogStatusInfo,
    ConfigStatusInfo,
    GitStatusInfo,
    WorktreeStatusResult,
)

pytestmark = pytest.mark.unit

STATUS_CASES = [
    pytest.param(
        FormatterCase(
            data=WorktreeStatusResult(
                root_dir=Path("/workspace/my-repo"),
                is_initialized=True,
                git=GitStatusInfo(is_git_repo=True, branch="main", is_dirty=False, uncommitted_files=0),
                config=ConfigStatusInfo(is_valid=True, config_path=Path("/workspace/my-repo/.worktree/config.json")),
                catalog=CatalogStatusInfo(exists=True, total_items=1),
                database=None,
                sandboxes=None,
            ),
            view=StatusView(
                health=StatusHealth.OK,
                root_dir=Path("/workspace/my-repo"),
                project_name="worktree-cli",
                warnings=[],
            ),
            render_expectations=["/workspace/my-repo", "worktree-cli"],
        ),
        id="healthy_workspace",
    ),
]

STATUS_PAYLOAD_CASES = [
    pytest.param(
        STATUS_CASES[0].values[0],
        {
            "health": "ok",
            "root_dir": "/workspace/my-repo",
            "project_name": "worktree-cli",
            "warnings": [],
        },
        id="healthy_workspace",
    ),
]


class WorktreeStatusFormatterTests:
    @pytest.mark.parametrize("case", STATUS_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[WorktreeStatusResult, StatusView]) -> None:
        """Verify transform derives the exact typed view model."""
        assert WorktreeStatusFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), STATUS_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[WorktreeStatusResult, StatusView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify wire format matches published schema as an exact literal dict."""
        assert WorktreeStatusFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", STATUS_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[WorktreeStatusResult, StatusView]) -> None:
        """Verify all non-null semantic view model values reach the Rich output."""
        rendered = render_rich(WorktreeStatusFormatter().to_rich(case.data))
        view = case.view

        if view.project_name is not None:
            assert view.project_name in rendered
        for warning in view.warnings:
            assert warning in rendered
```

Rules for Tier 2 tests:
- **No subclass overrides `to_json_serializable`**: formatters inherit this implementation from `ComponentFormatter` (`src/worktree/common/types.py`), which delegates to `self.transform(data).model_dump(mode="json")`. Overriding it in a subclass is forbidden and enforced by `tests/lint/test_formatter_contracts.py`.
- **Iterating collections inside a case**: statements like `for warning in case.view.warnings: assert warning in rendered` verify items within a single test scenario. This is permitted and is not the banned `for`-loop-over-scenarios pattern.
- **Wire format literals**: `test_json_payload_matches_published_shape` must assert against an exact literal dictionary, never `== case.view.model_dump(...)`, to guarantee serialization stability for field names, enum values, and null representations.

### Tier 3 - CLI Wiring (Dual-Tier Matrix)

Every command module must implement the dual-tier matrix (`scratch/test-structure-proposal.md` §11.1):

- `*RootTests` (e.g. `DiffCommandRootTests`): direct unit tests for pure Python command handlers (from `commands/<action>.py`) taking `CliContext`, bypassing Typer CLI runner overhead. Tagged `pytestmark = pytest.mark.unit`.
- `*CliIntegrationTests` (e.g. `DiffCliIntegrationTests`): CLI integration tests invoking `runner.invoke(app, [...])` to verify Click/Typer options, argument parsing, exit codes, and output dispatching. Tagged `pytestmark = pytest.mark.cli`.

Both tiers are required per command. Direct handler calls cannot see option binding, exit codes, or dispatcher wiring; runner tests verify wiring without duplicating domain logic. Four scenarios per command:
1. Happy path exit 0.
2. Failure path with expected non-zero exit code.
3. `--output-format json` emits valid JSON matching wire schema.
4. Any interactive confirmation or abort branch.

### Tier 4 - Invariants (`tests/lint/`)

- Static AST analysis and architectural boundary enforcement tests.
- Checks:
  - Layer isolation: `src/worktree/core/` and tests for core never import `worktree.cli.*`.
  - Output routing: zero direct `print()`, `typer.echo()`, or `click.echo()` outside `src/worktree/cli/ui/dispatcher.py`.
  - Result hierarchy: all `*Result` models inherit from `BaseResult`.
  - Remediation capitalization: all remediation fix suggestions begin with a capital letter.
  - Doc parity: `wt --help` command registration vs `README.md` command documentation parity.
- Marker: `pytestmark = pytest.mark.invariant`.

---

## Test Harness and Assertion Helpers

### Fluent Builders Harness (`tests/harness/builders.py`)

Construct domain objects in tests using fluent builders rather than raw dictionaries, ad-hoc keyword arguments, or monkeypatching internal state (`scratch/test-structure-proposal.md` §3.1):

- **Sensible baseline defaults:** Builders initialize a valid, complete domain object by default.
- **Chained mutations:** Tests explicitly state only the variations relevant to the test condition.
- **Immutable construction:** Calling `.build()` returns the validated Pydantic model.

Example patterns:

```python
# Workspace builder
workspace = (
    WorkspaceBuilder(tmp_path / "custom")
    .with_project_name("demo-project")
    .with_database()
    .with_catalog_templates()
    .with_git()
    .build()
)

# Step builder
step = (
    StepBuilder.command("echo test")
    .with_id("step-1")
    .with_timeout(30)
    .with_retry(max_retries=3, backoff_ms=100)
    .assert_exit_code(0)
    .assert_output_contains("success")
    .build()
)

# Step builder with template inheritance
inherited_step = StepBuilder.uses("wt/ai-code-patcher").with_id("patch").build()

# Blueprint builder
blueprint = (
    BlueprintBuilder.workflow("build-and-test")
    .with_input("environment", default="production", required=True)
    .with_step(StepBuilder.command("echo hi"))
    .build()
)
```

### Shared Contract Assertion Helpers (`tests/harness/assertions.py`)

Standardize assertions on contracts using shared helpers:

- **`assert_result_ok(result, expected_status=None)`**: Asserts `result.ok is True`, `len(result.errors) == 0`, and verifies `result.status == expected_status` if specified.
- **`assert_result_error(result, expected_code=None, *, expected_status=None)`**: Asserts `result.ok is False`, `len(result.errors) > 0`, verifies `result.status == expected_status` if specified, and asserts that `expected_code` matches an error code or substring in `result.errors`.
- **`assert_model_equal(actual, expected, *, exclude=None)`**: Compares Pydantic model instances directly or against an expected dictionary with clean mismatch diffs. If `exclude` is specified, it explicitly drops non-deterministic fields (e.g. timestamps, dynamic UUIDs) to prevent masking regressions.
- **`assert_exact_json(actual, expected_dict)`**: Guarantees exact byte/key wire-format contracts without ignoring unexpected extra keys.

### Determinism & Process Isolation Strategy

- **No hardcoded sleeps:** Step backoff and retry intervals utilize an injectable `VirtualClock` (`scratch/test-structure-proposal.md` §3.3). In tests, time advances synthetically without calling OS `sleep()`.
- **Process cleanup:** Subprocess tests register process handles with `process_registry`. The test harness runs a teardown hook ensuring spawned OS process groups receive `SIGKILL` on cleanup, preventing orphaned background processes.
- **Environment isolation:** Tests validating secrets (e.g. API keys) use pytest's `monkeypatch` fixture to isolate environment variables.

### Rich Render Assertions

- **Pinned width:** `render_rich(renderable, width=160)` renders to plain text via a real `Console`. **This is the only supported way to capture rendered output.**
- Console width for rendered assertions is authoritatively pinned to 160. Tests must not rely on ambient terminal size or in-process `os.environ["COLUMNS"]` mutations (`tests/conftest.py` does not mutate `os.environ`).
- `pytest-env` in `pyproject.toml`, `tasks.py` (`inv test`), and CI (`.github/workflows/ci.yml`) set `COLUMNS = "160"` and `PYTHONIOENCODING = "utf-8"` uniformly.

### Fixtures and Scope

- **Shared fixtures in `tests/conftest.py`:**
  - `isolated_workspace(tmp_path)`: Ephemeral workspace root directory initialized with `.worktree/` and its standard subdirectories (`.meta`, `sessions`, `artifacts`, `tmp`, `logs`, `sandboxes`, `catalog`).
  - `git_repo(tmp_path)`: Clean Git repository on branch `main` with configured `user.name` ("Test User"), `user.email` ("test@example.com"), and an initial root commit containing `README.md`.
  - `cli_runner()`: Preconfigured Typer `CliRunner` with `env={"NO_COLOR": "1", "COLUMNS": "160"}` to ensure deterministic terminal width and no ANSI escape sequences.
- **Keep domain fixtures close to their tests:** When setup logic is specific to a single test module, define it locally in that module or class.
- **Yield transparent handles:** Fixtures should establish baseline state and yield plain tuples or paths instead of opaque wrappers.
- **Baseline + inline mutation:** Establish a valid working baseline in the fixture. Tests covering edge or error conditions explicitly mutate the handle in the test body.
- **Legacy helper deprecation:** Legacy helper modules (`tests/helpers/legacy.py`, `make.py`, old `git_fs`/`fs` wrappers) are obsolete and must not be referenced or extended in new tests.

---

## Parameterization as Primary Approach

Parameterization via `@pytest.mark.parametrize` is the primary, default approach for exercising contracts across varying conditions. "One test = one behaviour" means **one test function asserts one behavioral contract across its parameter space**, not *one Python function per scenario*.

### Decision Heuristic: When to Parameterize vs. When to Split

| Pattern | Approach | Rationale |
|---|---|---|
| **Input & Boundary Matrices** | `@pytest.mark.parametrize` | Testing the same function with varying valid/invalid inputs or boundary values. |
| **Error / Code Permutations** | `@pytest.mark.parametrize` | Verifying that multiple invalid states each raise `AssertionError` or return specific error codes. |
| **Type Polymorphism** | `@pytest.mark.parametrize` | Testing an operation against alternative supported representations (e.g. `BaseModel` vs `dict`). |
| **Configuration / CLI Options** | `@pytest.mark.parametrize` | Testing flags or options that produce proportional, predictable variations in output. |
| **Divergent Fixtures / State** | Separate `def test_*` | When one case requires a specialized fixture (e.g. initialized Git repo) while another runs in memory. |
| **Different Lifecycles / Workflows** | Separate `def test_*` | Multi-step orchestration, cancellation flows vs normal completion, signal traps. |
| **Protocol Trios (Tier 2)** | Separate `def test_*` | Pinned tripartite contracts (transform equality, JSON wire literal, Rich render) per formatter. |

#### Parameterization Invariants
- **Explicit, descriptive IDs:** Always wrap parameterized cases in `pytest.param(..., id="descriptive_case_id")` with a clear, descriptive `id`.
- **Strict typing:** Annotate test signatures tightly without broad `Any` (e.g., `DummyModel | dict[str, object]`).
- **No conditional assertion branching:** Do not combine fundamentally divergent assertion contracts into one parameterized test using complex `if/else` inside the test body; if the assertion topology diverges, split into distinct test methods.

---

## Core Testing Rules

- **Parameterize sibling variations; separate tests for distinct behaviors.** One test asserts one contract across its parameter space. Multiple scenarios go in `@pytest.mark.parametrize`, never a `for` loop, never stacked assertions, and never copy-pasted sibling functions differing only by inputs. Always wrap parameterized cases in `pytest.param(..., id="descriptive_case_id")` with a clear, descriptive `id`.
- **Compare the object, not its fields.** When testing operations that return a model or result, write `assert result == Expected(...)` or `assert_model_equal(result, expected)` rather than asserting individual fields. One comparison is stronger than N assertions (it also fails on unexpected extra fields) and gives a readable diff.
- **No test seams in production code.** Never add a parameter, kwarg, or callback solely for test injection. Monkeypatch collaborators at module boundaries instead. A parameter production never reads is dead code with a test attached.
- **A seam is not tested until a test proves a real caller uses it.** Asserting a callback was stored is not a test. Assert it fires, from the production path.
- **Test doubles must be types production actually passes.** If production passes `Console`, tests pass `Console`. Never build a stub whose interface is the union of every branch in a `hasattr` chain. If a double is genuinely needed, it implements a Protocol production is typed against.
- **No test may be the sole consumer of a production symbol.** If deleting the test would make production code unreachable, the production code is dead. Delete both.
- **Never write negative existence tests for deleted symbols.** Tests assert the contracts and behaviors of the current codebase, not the historical outcome of a refactor. When dead or obsolete functions, classes, or aliases are removed from production, delete the tests that called them. Do not replace them with assertions checking that the symbol is gone (`assert not hasattr(mod, "old_fn")`).
- **No reaching into private state.** No `obj._attr` assertions, no importing underscore-prefixed symbols. If a private helper is worth testing, it is worth making public.
- **Machine-readable output byte-exact, human-readable output by data presence.** Two contracts, two strictnesses. Never scrape human output for exactness; never accept substring matching for machine output.
- **The name and docstring are part of the assertion.** If the name says "terminates child process tree", a reviewer must be able to point at the line that checks the child died.
- **`is not None` is not an assertion.** If it is the only assert, the test is unfinished.
- **`isinstance` only when it distinguishes two real code paths.** `basedpyright` already proves the rest.
- **Annotate test helpers as tightly as production.** Give fixtures real return types and type helper parameters against what production passes. Permitted and banned uses of `Any` are in `code-conventions.md` and apply to `tests/` unchanged.
- **Do not `# pyright: ignore` a test-tree error to make the checker pass.** If the checker rejects a fixture or helper, the fixture is wrong. The one exception is testing an intentionally ill-typed call (`pytest.raises(TypeError)`).
- **Never assert help text wording.** Assert command registration and option names via Click metadata. The one exception is the `wt --help` vs `README.md` check in `tests/lint/`.
- **Cover every branch** of a factory, dispatcher, or `elif` chain. A covered line in a two-branch function proves nothing.
- **No hardcoded sleeps.** Monkeypatch the clock (`time.monotonic` / `asyncio.sleep`) or use `VirtualClock`.

---

## Running Tests and Coverage Gates

```bash
inv test                            # full suite, parallel (xdist)
inv test --no-parallel              # serial (faster for a single module)
inv test --coverage                 # coverage report (inv test -c)
inv test --fast-fail                # stop on first failure (-x)
pytest -m unit                      # run only in-memory unit tests
pytest -m "not slow"                # run suite excluding slow integration tests
python -m pytest -q <path>          # a specific file or directory
```

- Global coverage floor is **>= 80%** (`fail_under = 80` in `pyproject.toml`).
- Branch coverage is **enabled** (`branch = true` under `[tool.coverage.run]`).
- Coverage is a **regression backstop, not an optimization goal**. Do not add tests solely to raise the percentage. Prefer tests that lock real behavior and regressions.
- **A coverage drop from deleting dead code is a success.** Read it that way.

---

## PR Review Hygiene and Testing Documentation Review Rule

Every pull request and ticket in this milestone touching tests must verify compliance with this document (`docs/agents/testing.md`) and `scratch/test-structure-proposal.md` (§12.1 Rule 7). Reviewers and implementers must audit tests against this checklist:

1. **1:1 Parity**: Does the test file mirror `src/worktree/` exactly?
2. **Execution Tiers**: Are CLI tests split into `*RootTests` and `*CliIntegrationTests`? Do formatters follow the 3-test `FormatterCase` protocol?
3. **Naming**: Are classes named `*Tests` and methods named `test_<condition>_<outcome>` with banned vague names avoided?
4. **Contract Assertions**: Are assertions checking contracts (`BaseResult`, exact JSON payload dicts, exit codes, disk state) without reaching into private attributes or scraping Rich formatting?
5. **Harness Hygiene**: Are tests using standard fixtures (`tmp_path`, `GitWorkspaceHarness`) and shared assertion helpers rather than legacy helper modules?
