# Testing

Testing conventions, fixtures, and execution patterns for Worktree CLI.

---

## The rule that matters most

**Test at contracts, not at implementation.** A contract is a boundary we chose
deliberately: a `BaseResult` object, a JSON payload, an exit code, a file on
disk, a git ref. Implementation is everything else: rendered layout, private
helpers, call ordering, constructor assignments.

Asserting on implementation costs brittleness and buys no safety. A suite can
reach 90% line coverage while missing every real defect, and this one has.

---

## Layout and Naming

**Relevant sources:** `tests/`, `pyproject.toml`

- Test structure mirrors `src/worktree/` under `tests/`
  (`src/worktree/core/config/` -> `tests/core/config/`). **A test lives beside
  what it tests.** If a module moves package, its test moves in the same commit.
- Every test directory gets an `__init__.py`. Basenames repeat across the tree
  (`test_formatters.py`, `test_filesystem.py`), so collection depends on the
  packages being real.
- **Pick one class-naming convention: `*Tests`.** `pyproject.toml` sets
  `python_classes = ["Test*", "*Tests"]`, so both collect and the suite uses
  both. Two spellings make "is there already a test class for this?" a two-query
  question, which is how `AtomicWriteJsonTests` came to exist twice. `*Tests` is
  already dominant, so standardize there and rename the `Test*` minority.
  Standalone `test_*` functions are still preferred over either.
- **One test file per source module.** Do not split one module's tests across
  files without a stated rule; three files covering `Filesystem` is how a
  duplicate class survived.
- `tests/core/**` must never import `worktree.cli.*`.

### Organizing Command Tests by Tier

Organize CLI command test modules into clear execution tiers to aid comprehension:

- `*RootTests` (e.g. `DiffCommandRootTests`): direct unit tests for pure Python
  command handlers (from `commands/root.py`) taking `CliContext`, bypassing
  Typer CLI runner overhead.
- `*CliIntegrationTests` (e.g. `DiffCliIntegrationTests`): CLI integration tests
  invoking `runner.invoke(app, [...])` to verify Click/Typer options, argument
  parsing, exit codes, and output dispatching.

Both tiers are required per command. A direct handler call cannot see option
binding, exit codes, or dispatcher wiring.

---

## The four tiers

Different subject, different mocking policy, different assertion style. Do not
mix them in one test.

### Tier 1 - Domain behavior (most tests)

- **Subject:** services and facades under `core/`.
- **Assert on:** the returned `BaseResult` (status, errors, fixes, fields) and
  real side effects: files written, git refs created, DB rows.
- **Mocks:** none, except genuine process or network boundaries. Use `git_fs` / `fs`.

### Tier 2 - Presentation contracts (two tests per formatter, never one)

- **JSON:** assert `to_json_serializable(model)` as an **exact dict**. This is a
  promise to other programs; exactness is the point and it catches accidental
  new fields.
- **Rich:** render at a pinned width and assert **only values that came from the
  model** (ids, names, counts, error text). Never assert a label, border, glyph,
  padding, or a full sentence.

### Tier 3 - CLI wiring (`CliRunner`, four per command)

Happy path exit 0; one failure path with the right non-zero exit;
`--output-format json` parses; any confirm/abort path. Keep thin - Tier 1 owns
the logic.

### Tier 4 - Invariants (`tests/lint/`)

Import boundaries, no-dead-code, formatter-registration completeness,
`wt --help` vs `README.md`. Cheapest tests in the repo; they catch categories,
not instances. Grow this directory.

---

## Test Rules

- **One test = one behaviour.** Multiple scenarios go in
  `@pytest.mark.parametrize`, never a `for` loop and never four asserts in a
  row - you need to know *which* case failed.
- **Compare the object, not its fields.** If you are about to assert 8 fields of
  one result, write `assert result == Expected(...)` or
  `assert result.model_dump() == {...}`. One comparison is *stronger* than N
  assertions (it also fails on unexpected extra fields) and gives a readable
  diff instead of stopping at the first mismatch. Pydantic models support `==`.
- **No test seams in production code.** Never add a parameter, kwarg, or
  callback solely for test injection. Monkeypatch collaborators at module
  boundaries instead. A parameter production never reads is dead code with a
  test attached.
- **A seam is not tested until a test proves a real caller uses it.** Asserting
  a callback was *stored* is not a test. Assert it *fires*, from the production
  path.
- **Test doubles must be types production actually passes.** If production
  passes `Console`, tests pass `Console`. Never build a stub whose interface is
  the union of every branch in a `hasattr` chain - it guarantees tests and
  production take different paths. If a double is genuinely needed, it
  implements a Protocol production is typed against, so the type checker keeps
  them aligned.
- **No test may be the sole consumer of a production symbol.** If deleting the
  test would make production code unreachable, the production code is dead.
  Delete both.
- **No reaching into private state.** No `obj._attr` assertions, no importing
  underscore-prefixed symbols. If a private helper is worth testing, it is worth
  making public.
- **Machine-readable output byte-exact, human-readable output by data presence.**
  Two contracts, two strictnesses. Never scrape human output for exactness;
  never accept substring matching for machine output.
- **The name and docstring are part of the assertion.** If the name says
  "terminates the child process tree", a reviewer must be able to point at the
  line that checks the child died. A name that overstates the body is worse than
  no test: it forecloses the audit. When you copy a test, change the *inputs*,
  not just the name - a renamed duplicate is how an untested branch hides.
- **`is not None` is not an assertion.** If it is the only assert, the test is
  unfinished.
- **`isinstance` only when it distinguishes two real code paths.** `basedpyright`
  already proves the rest.
- **Annotate test helpers as tightly as production.** Once `tests/` is inside
  `[tool.basedpyright]`'s `include`, an `Any` in a fixture or helper propagates
  into every test that uses it, so the checker stops protecting the suite. Give
  fixtures real return types (`Iterator[GitFileSystem]`, not `None`) and type
  helper parameters against what production passes. A `MagicMock` in a signature
  is the same finding as a hand-rolled stub: see "Test doubles must be types
  production actually passes" above. Permitted and banned uses of `Any` are in
  [code-conventions.md](code-conventions.md#type-annotations-and-any) and apply
  to `tests/` unchanged.
- **Do not `# pyright: ignore` a test-tree error to make the checker pass.**
  If the checker rejects a fixture or helper, the fixture is wrong; give it
  the type production passes. The one exception is a test whose *subject* is
  an ill-typed call (`pytest.raises(TypeError)`, Pydantic `extra="forbid"`).
  Prefer `Model.model_validate({...})` when that path exists. Permitted and
  banned suppressions are in
  [code-conventions.md](code-conventions.md#type-checker-suppressions).
- **Never assert help text wording.** Assert command registration and option
  names via Click metadata. The one exception is the `wt --help` vs `README.md`
  check required by AGENTS.md.
- **Cover every branch** of a factory, dispatcher, or `elif` chain. A covered
  *line* in a two-branch function proves nothing.
- **No hardcoded sleeps.** Monkeypatch the clock; see
  `tests/core/step/test_runner.py` for the pattern.
- **Use global helpers with kwargs overrides** for common object setup.

---

## Fixtures

**Relevant sources:** `tests/conftest.py`, `tests/helpers.py`

- `git_fs` (`GitFileSystem`): real git repo in a temp dir, copied from a
  session-scoped template. Provides `init_repo()`, `create_config_file()`,
  `create_step_file()`, `create_workflow_file()`.
- `fs` (`FileSystem`): plain temp filesystem.
- `render_rich(renderable, width=160)`: renders to plain text via a real
  `Console`. **This is the only supported way to capture rendered output.**
  Console width for rendered assertions is authoritatively pinned to 160 by
  `tests/helpers.py` (`render_rich`). Tests must not rely
  on ambient terminal size or in-process `os.environ["COLUMNS"]` mutations
  (`tests/conftest.py` does not mutate `os.environ`). `pytest-env` in
  `pyproject.toml`, `tasks.py` (`inv test`), and CI (`.github/workflows/ci.yml`)
  set `COLUMNS = "160"` and `PYTHONIOENCODING = "utf-8"` uniformly across all
  test invocations.
- Prefer real filesystem and git over mocks.

### Fixture Scoping and Reuse

- **Keep domain fixtures close to their tests**: when setup logic is specific to
  a single test module, define it locally in that module or class.
- **Promote duplicated fixtures to common/global**: do **not** duplicate
  identical fixtures across multiple test modules. If an exact setup pattern is
  needed across multiple modules or domains, promote it to `tests/conftest.py`
  or factor the setup logic into `tests/helpers.py`.
- **Yield transparent handles**: fixtures should establish baseline state and
  yield plain tuples or dataclasses (e.g. `yield patch_file, context`) instead
  of opaque harness wrappers or performing hidden assertions.
- **Baseline + inline mutation**: establish a valid, working baseline in the
  fixture. Tests covering edge or error conditions should explicitly mutate the
  handle in the test body rather than creating a proliferation of
  near-identical fixtures or parameterized boolean switches.

---

## CLI and Rich Output Testing

### Subcommands and `--help`

Assert command **registration** and **option names** via Click metadata rather
than parsing stdout. Do not assert the help *sentence* - that is copy, and it
moves:

```python
from typer.main import get_command
from worktree.cli import app

cmd = get_command(app).get_command(None, "sandbox").get_command(None, "list")
assert cmd is not None
assert {param.name for param in cmd.params} >= {"output_format"}
```

### Rich Tables and Panels

- Render through `render_rich(...)` (or a `Console` with an explicit `width=`)
  so layout assertions do not vary with the developer's terminal.
- Assert only model-derived values. Labels, borders, glyphs, padding, and full
  sentences are layout, not contract.

---

## Model to follow

`tests/core/config/test_config_schema.py` is the reference file. Its method -
one canonical valid input, mutate exactly one field, assert the failure is
path-qualified through a custom assertion helper, then pin the models against
the same schema - is what contract testing looks like here. Copy it.

---

## Running Tests

**Relevant sources:** `tasks.py`, `pyproject.toml`

```bash
inv test                            # full suite, parallel (xdist)
inv test --no-parallel              # serial (faster for a single module)
inv test --coverage                 # coverage report (inv test -c)
inv test --fast-fail                # stop on first failure (-x)
python -m pytest -n auto tests/ -q <path>   # a specific file or directory
```

- Global floor is **>= 80%** (`fail_under` in `pyproject.toml`). Changed lines
  should be held to a higher bar; the global number is a floor, not the target.
- Branch coverage is **not yet enabled** (`branch = false` under
  `[tool.coverage.run]`). Until it is, branch gaps do not show up in the report
  at all, so cover them deliberately rather than trusting the percentage.
- Coverage is a **regression backstop, not an optimization goal**. Do not add
  tests to raise the percentage.
- **A coverage drop from deleting dead code is a success.** Read it that way.
