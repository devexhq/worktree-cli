# Testing

Testing conventions, fixtures, and execution patterns for Worktree CLI.

---

## Layout and Naming

**Relevant sources:** `tests/`, `pyproject.toml`

- Test structure mirrors `src/worktree/` under `tests/` (e.g. `src/worktree/core/config/` -> `tests/core/config/`).
- Use domain-specific file basenames (e.g. `test_init_command.py`) to avoid collection collisions without `__init__.py` files.
- Test classes must match `Test*` or `*Tests`; standalone `test_*` functions are preferred.

### Organizing Command Tests by Tier
Organize CLI command test modules into clear execution tiers to aid comprehension:
- `*RootTests` (e.g. `DiffCommandRootTests`): Direct unit tests for pure Python command handlers (from `commands/root.py`) taking `CliContext`, bypassing Typer CLI runner overhead.
- `*CliIntegrationTests` (e.g. `DiffCliIntegrationTests`): CLI integration tests invoking `runner.invoke(app, [...])` to verify Click/Typer options, argument parsing, exit codes, and output dispatching.

---

## Test Rules

- **One test = one behaviour**: Keep assertions focused on a single logical outcome.
- **No test seams in production code**: Never add parameters (including constructor kwargs) solely for test injection; monkeypatch collaborators at module boundaries instead.
- **No reaching into private state**: Use public factories, constructors, and fixtures to build and assert state.
- **Avoid hardcoded sleeps and timeouts**: Slows down the test suite and introduces flakiness.
- **Use global test helpers with kwargs overrides**: Factor common test object setups into helper functions with parameter overrides.
- **Highlight scenario delta, extract incidental plumbing**: Factor repetitive filesystem and context scaffolding into fixtures yielding actionable handles (e.g. `tuple[Path, CliContext]`). Keep tests explicit: the test executes the action and asserts the outcome. For edge/variant cases, apply modifications directly in the test body (e.g. `patch_file.write_text("")`) so the reader immediately spots what makes the scenario unique without diffing boilerplate.

---

## Fixtures

**Relevant sources:** `tests/conftest.py`, `tests/helpers.py`

- `git_fs` (`GitFileSystem`): Initialized Git repository in a temp directory (`.base_path`). Provides `init_repo()`, `create_config_file()`, `create_step_file()`, `create_workflow_file()`.
- `fs` (`FileSystem`): Plain temporary filesystem fixture.
- Prefer real filesystem and Git operations via `git_fs`/`fs` over over-mocking.

### Fixture Scoping and Reuse
- **Keep domain fixtures close to their tests**: When setup logic is specific to a single test module, define it locally in that module or class.
- **Promote duplicated fixtures to common/global**: Do **not** duplicate identical fixtures across multiple test modules. If an exact setup pattern is needed across multiple modules or domains, promote it to `tests/conftest.py` or factor the setup logic into `tests/helpers.py`.
- **Yield transparent handles**: Fixtures should establish baseline state and yield plain tuples or dataclasses (e.g. `yield patch_file, context`) instead of opaque harness wrappers or performing hidden assertions.
- **Baseline + inline mutation**: Establish a valid, working baseline in the fixture. Tests covering edge or error conditions should explicitly mutate the handle in the test body rather than creating a proliferation of near-identical fixtures or parameterized boolean switches.

---

## CLI and Rich Output Testing

**Relevant sources:** `src/worktree/common/utils.py` (`RichOutput`)

### Subcommands and `--help`
- Assert command registration, help strings, and options via **Click metadata** rather than parsing stdout:
  ```python
  from typer.main import get_command
  from worktree.cli import app

  cmd = get_command(app).get_command(None, "sandbox").get_command(None, "list")
  assert cmd.help == "List tracked sandboxes and their lifecycle status."
  ```

### Rich Tables and Panels
- Renderers tested for exact layout should inject a fixed-width console (`Console(width=80, force_terminal=False)`) to prevent failures across variable terminal widths.
- Prefer asserting on structured results over screen-scraped Rich strings.

---

## Running Tests

**Relevant sources:** `tasks.py`, `pyproject.toml`

```bash
inv test                            # run full test suite with parallelization (xdist)
inv test --no-parallel              # run serially (faster for isolated test runs)
inv test --coverage                 # run with coverage report (inv test -c)
inv test --fast-fail                # stop on first failure (-x)
python -m pytest tests/ -q <path>   # run a specific test file or directory
```

- Total coverage must remain **>= 80%** (`fail_under = 80` in `pyproject.toml`).
- Coverage is a **regression backstop**, not an optimization goal. Add tests for behavior, edge cases, and failure modes rather than busywork lines.
