# Testing

## Layout and naming

Tests mirror the source tree under `tests/` (e.g. `getworktree/core/db/` ->
`tests/core/test_token_db.py`). Prefer domain-specific basenames
(`test_init_command.py`, not `test_command.py`) so pytest collection stays unique
without package `__init__.py` files. Test classes must be named `Test*` or
`*Tests` per `python_classes` in [pyproject.toml](../../pyproject.toml); plain
`test_*` functions work too.

## Test Rules

Follow these rules:
- One test = one behaviour
- Do not reach into private/internal attributes to set up or assert state. Prefer a public constructor, factory, or fixture that produces the state you need.
- Avoid using timeouts where there is a better option available, they slow down the test suite
- Opt to create global test helpers that allow for per-parameter override instead of bloated test setups. See the example below.
- Never modify production function/class signatures to add a test seam - use mocks and patches instead
- When using mocks/patches, avoid asserting it was called unless materially relevant to the test. Assertions should focus on the business logic under test.

Example global helper:
```
def make_dummy_session(git_repo: Path, **kwargs) -> SandboxSession:
    """Generates a default valid session. Override specific fields via kwargs."""
    defaults = {
        "session_id": "wf-default-101",
        "target_branch": "wt/default-branch",
        "sandbox_path": git_repo / ".worktree" / "sandboxes" / "wf-default-101",
        "base_commit": "HEAD",
        "created_at": "2026-08-05 12:00:00",
    }
    defaults.update(kwargs)
    return SandboxSession(**defaults)

# USAGE IN TEST
session = make_dummy_session(git_repo, session_id="wf-fail-202")
```

## Fixture style

Prefer real integration over mocking: fixtures create a real Git repo in `tmp_path`
via `subprocess.run(["git", "init"], ...)` and use `monkeypatch.chdir` to point
commands at it. See [tests/cli/init/test_init_command.py](../../tests/cli/init/test_init_command.py)
for the canonical `git_repo` fixture.

## CLI help and Rich output

CI runners often use a **narrow `COLUMNS`**. Rich help and tables wrap or
truncate option names, headers, and cell values there, so substring asserts on
rendered text flake even when the command is correct.

### Typer / Click registration and `--help`

- Prefer **Click metadata** over parsing `CliRunner` stdout from `--help`.
- Use `typer.main.get_command(app)` and walk subcommands with
  `.get_command(None, "…")`.
- Assert `cmd.help` and option names from `param.opts` /
  `param.secondary_opts` (and `list_commands` for groups).
- Still invoke `--help` once and assert `exit_code == 0` if you want a smoke
  check that help renders without raising.

Canonical examples:

- [tests/cli/workflow/test_workflow_run_command.py](../../tests/cli/workflow/test_workflow_run_command.py)
  (`WorkflowRunCliTests.test_help_text`)
- [tests/cli/sandbox/test_sandbox_list_command.py](../../tests/cli/sandbox/test_sandbox_list_command.py)
  (`SandboxListCliTests`)

```python
from typer.main import get_command
from typer.testing import CliRunner

from getworktree.cli import app

runner = CliRunner()


def test_list_help() -> None:
    result = runner.invoke(app, ["sandbox", "list", "--help"])
    assert result.exit_code == 0

    list_cmd = get_command(app).get_command(None, "sandbox").get_command(None, "list")
    assert list_cmd.help == "List tracked sandboxes and their lifecycle status."
    opts: set[str] = set()
    for param in list_cmd.params:
        opts.update(param.opts)
        secondary = getattr(param, "secondary_opts", None) or ()
        opts.update(secondary)
    assert "--status" in opts
```

Do **not** assert `assert "--status" in result.stdout` (or similar) for Rich
help — under small terminals the flag can wrap mid-token and disappear from a
simple substring check.

### Tables and other Rich renderers

- Prefer asserting **structured results** from collect/core helpers (row order,
  statuses, exit codes) rather than ambient `capsys` table dumps for business
  logic.
- When you must lock renderer copy or columns, inject a
  `RichOutput(Console(file=StringIO(), width=…, force_terminal=False, …))`
  (or an equivalent fixed-width console) so layout does not depend on CI
  `COLUMNS`.
- See init/sandbox renderer tests for the fixed-console pattern:
  [tests/cli/init/test_init_renderers.py](../../tests/cli/init/test_init_renderers.py),
  [tests/cli/sandbox/test_sandbox_list_command.py](../../tests/cli/sandbox/test_sandbox_list_command.py)
  (`SandboxListRenderTests`).

Stable empty-state / panel titles (`No sandboxes found.`,
`Worktree Not Initialized`) are fine to assert on stdout; full table cell
contents and help option lists are not, unless width is controlled.

## Running tests

```bash
inv test                            # invoke task, tasks.py
inv test --coverage                 # adds --cov=getworktree --cov-report=term-missing
inv test --fast-fail                # stop on first failure
python -m pytest tests/ -q {file}   # equivalent, no invoke dependency
```

Prefer running targetted tests during iterations, do not run the full test-suite until the end.

Total coverage must stay at **≥ 80%** (`fail_under = 80` in
[pyproject.toml](../../pyproject.toml) under `[tool.coverage.report]`). Coverage
runs fail the process if the floor is missed.

### Coverage philosophy

The 80% floor is a **regression backstop**, not an optimization target.

- **Do** add tests for changed behavior, public command contracts, failure exits,
  and state-corrupting paths (real `git` / `tmp_path` when practical).
- **Do not** add tests solely to move a line from red to green, assert on
  incidental Rich copy, or over-mock until the test only proves the mock ran.
- If coverage drops below 80% after a real change: cover the **risk** you
  introduced, or deliberately leave defensive/unreachable code uncovered—do not
  pad with low-value tests.
- Treat missing lines in the coverage report as a **review checklist**, not a
  ticket queue.

CI runs `python -m pytest --cov=getworktree --cov-report=term-missing --cov-report=xml tests/ -q`
— match this locally before pushing.
