# Code Conventions

## Pydantic models

Every result/outcome model sets:

```python
model_config = {"extra": "forbid", "strict": True}
```

This catches typos in constructed payloads and unexpected extra keys early.
Follow this for any new `BaseModel` you add.

## Result/Outcome pattern

Operations that can partially succeed return a Pydantic result object instead of
raising, e.g. `BootstrapResult`, `ConfigGenerationResult`, `WorkflowSeedResult`,
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
and `_atomic_write_text` in `core/workflows/seeder.py` for the pattern.

## Console output

All CLI output goes through `RichOutput` ([getworktree/common/utils.py](../../getworktree/common/utils.py))
or a shared `rich.console.Console` — no bare `print()`. Use `RichOutput.error_panel`
for failures so error formatting stays consistent across commands.


## Error and status messages

Prefer **inline f-strings** (or plain string literals) at the call site when
building user-facing `errors` / `warnings` entries. Do **not** add private
helpers whose only job is to format a single message template
(e.g. `_invalid_diff_error(detail) -> str`).

Good (see `core/workflows/metadata.py`):

```python
return WorkflowMetadataParseResult(
    status=WorkflowMetadataStatus.NOT_FOUND,
    source_path=source_path,
    errors=[
        f"Workflow definition not found at '{source_path}' (WORKFLOW_META_NOT_FOUND)."
    ],
)
```

Also good — multi-line guidance with adjacent string literals:

```python
errors = (
    [
        f"Patch is not a valid unified diff: {parse_error}\n"
        "Fix:\n"
        "- return a standard unified diff (diff --git / --- +++ / @@ hunks)"
    ],
)
```

Avoid:

```python
def _invalid_diff_error(detail: str) -> str:
    return f"Patch is not a valid unified diff: {detail}\nFix:\n- ..."


errors = [_invalid_diff_error(parse_error)]
```

Rules of thumb:

- Keep stable machine-oriented tokens in the string (`WORKFLOW_META_*`,
  `TRIGGER_*`, `AGENT_PROVIDER_ERROR`, `CONFIG_SCHEMA_INVALID`, …).
- A short local binding for shared prep is fine
  (`detail = "; ".join(...)`; `joined = ", ".join(paths)`), then inline the
  final message.
- Still use real helpers when they do non-trivial work beyond formatting
  (e.g. `_semantic_errors` collectors, presentation helpers like
  `format_error_lines`).
- Do **not** introduce a shared error-catalog module of formatters; that
  recreates the pattern this convention removes.
- Do **not** import private `_…_error` helpers across modules.

## Docstrings and imports

- Docstrings follow the Google convention, enforced by ruff's `D` rules
  (`[tool.ruff]` in [pyproject.toml](../../pyproject.toml)). `__init__.py`,
  `tests/*`, and `setup.py` are exempt.
- `getworktree` is registered as first-party for isort; keep local imports grouped
  accordingly and let `ruff format`/`ruff check --fix` handle ordering.
