# Code Conventions

## Pydantic models

Every DTO/result model sets:

```python
model_config = {"extra": "forbid", "strict": True}
```

This catches typos in constructed payloads and unexpected extra keys early.
Follow this for any new `BaseModel` you add.

## Result/Outcome pattern

Operations that can partially succeed return a Pydantic result object instead of
raising, e.g. `BootstrapResult`, `ConfigGenerationResult`, `LoopSeedResult`,
`ValidationResult`. The convention:

- Lists describing what happened: `created_files`, `dirs_existing`, `inserted_keys`, etc.
- `warnings: list[str]` for non-fatal issues.
- `errors: list[str]` for fatal issues.
- An `ok` property defined as `not self.errors`.

Callers check `.ok` and render `.errors`/`.warnings` rather than catching exceptions.
Reuse this shape for new core operations instead of introducing ad-hoc return types.

## File writes

Never write a config/state file directly. Write to a `.tmp` sibling, flush,
`os.fsync`, then `Path.replace` to swap it into place atomically. See
`atomic_write_json` in [getworktree/common/fs.py](../../getworktree/common/fs.py)
and `_atomic_write_text` in `core/loops/seeder.py` for the pattern.

## Console output

All CLI output goes through `RichOutput` ([getworktree/common/utils.py](../../getworktree/common/utils.py))
or a shared `rich.console.Console` — no bare `print()`. Use `RichOutput.error_panel`
for failures so error formatting stays consistent across commands.

## Docstrings and imports

- Docstrings follow the Google convention, enforced by ruff's `D` rules
  (`[tool.ruff]` in [pyproject.toml](../../pyproject.toml)). `__init__.py`,
  `tests/*`, and `setup.py` are exempt.
- `getworktree` is registered as first-party for isort; keep local imports grouped
  accordingly and let `ruff format`/`ruff check --fix` handle ordering.
