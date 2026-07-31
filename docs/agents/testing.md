# Testing

## Layout and naming

Tests mirror the source tree under `tests/` (e.g. `getworktree/core/db.py` ->
`tests/core/test_token_db.py`). Prefer domain-specific basenames
(`test_init_command.py`, not `test_command.py`) so pytest collection stays unique
without package `__init__.py` files. Test classes must be named `Test*` or
`*Tests` per `python_classes` in [pyproject.toml](../../pyproject.toml); plain
`test_*` functions work too.

## Fixture style

Prefer real integration over mocking: fixtures create a real Git repo in `tmp_path`
via `subprocess.run(["git", "init"], ...)` and use `monkeypatch.chdir` to point
commands at it. See [tests/commands/init/test_init_command.py](../../tests/commands/init/test_init_command.py)
for the canonical `git_repo` fixture.

## Running tests

```bash
inv test                       # invoke task, tasks.py
inv test --coverage            # adds --cov=getworktree --cov-report=term-missing
inv test --fast-fail           # stop on first failure
python -m pytest tests/ -q     # equivalent, no invoke dependency
```

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
