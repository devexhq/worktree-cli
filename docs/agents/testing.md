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

CI runs `python -m pytest --cov=getworktree --cov-report=term-missing --cov-report=xml tests/ -q`
— match this locally before pushing.
