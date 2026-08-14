# Code Conventions

## Pydantic models

Every result/outcome model sets:

```python
model_config = {"extra": "forbid", "strict": True}
```

This catches typos in constructed payloads and unexpected extra keys early.
Follow this for any new `BaseModel` you add.

## Variable naming

Prefer self-explanatory variable names that clearly describe the contained value without requiring the reader to inspect surrounding code context. Avoid arbitrary or non-standard abbreviations.

- **Acceptable**: Standard conventions or transparent shorthands (`exc`, `rel_path`, `i`/`v` in list comprehensions or loops, `fs`, `cwd`, `db`).
- **Unacceptable**: Cryptic or truncated abbreviations (e.g. `val_res` instead of `validation_result`, `tf_str` instead of `type_filter_string`, `err_msg` instead of `error_message`, `tmpl` instead of `template`, `res` instead of `result`, `shas` instead of `checksum_hashes` or `record_shas`).

## Structure
Use standalone functions or classes / packages of modules where appropriate. A function or class that requires > 5 arguments should be refactored to accept an env/context/configuration object (frozen dataclass) instead. 

Do not create God-functions - opt instead to break down functionality into separate functions within a class or within the module if there is truly no shared logic that would warrant a class structure. `complexipy` (see [ci-and-tooling.md](ci-and-tooling.md)) is the mechanical check for this — if a function you touched shows up in a fresh run, extract before merging rather than leaving it for later.

Do not include test seams in function and class definitions. Production code should exercise production logic only, not test-related logic.

### Keep code DRY

Avoid useless repetition in production code. Before writing a new private helper, grep for an existing one with similar behavior in `common/` and in sibling packages — duplicated formatting/normalization helpers (e.g. two copies of the same warning-bullet formatter in two different modules, or the same `x.value if hasattr(x, "value") else str(x)` enum guard copy-pasted across every CLI renderer) are a recurring smell in this codebase. If two or more modules need the same small piece of logic:

- Put it in `common/` when it has no dependency on a specific domain package.
- Put it in the more foundational domain package (see the import-direction rule
  in [architecture.md](architecture.md#package-boundaries-import-direction)) and import it from there, rather than copying it forward.

### One model per concept

Before adding a new Pydantic model, check whether an existing model in `core/`
already represents the same domain concept (a "step", a "workflow run", etc.).
Two divergent models for the same concept living in different packages —
with mismatched required fields or different enum vocabularies for the same
idea — are worse than one model imported across a package boundary. Prefer
sharing the existing model, or explicitly replacing it in the same change,
over adding a second one.

## Result/Outcome pattern

Operations that can partially succeed return a Pydantic result object instead of
raising, e.g. `BootstrapResult`, `ConfigGenerationResult`, `SeedResult`,
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
and `_atomic_write_text` in `core/workflows/services/seeder.py` for the pattern.

## Console output

All CLI output goes through `RichOutput` ([getworktree/common/utils.py](../../getworktree/common/utils.py))
or a shared `rich.console.Console` — no bare `print()`. Use `RichOutput.error_panel`
for failures so error formatting stays consistent across commands.


## Error and status messages

Prefer **inline f-strings** (or plain string literals) at the call site when
building user-facing `errors` / `warnings` entries. Do **not** add private
helpers whose only job is to format a single message template
(e.g. `_invalid_diff_error(detail) -> str`).

This scales up, too: a function whose only job is assembling a large text
report by branching on input shape (e.g. building a multi-line `wt workflow
show` summary via a long chain of `if isinstance(...)` blocks appending to a
`list[str]`) is still a message-formatting function, just a bigger one — and
it will show up as a God-function in `complexipy`. Decompose it into one small
helper per section (header, warnings, steps, ...), each returning
`list[str]`, and keep the public function as a thin composer that
concatenates them. Don't let one function own the whole document.

Good (see `core/config/loader.py`):

```python
return ConfigLoadResult(
    status=ConfigLoadStatus.NOT_FOUND,
    config_path=path,
    errors=[f"Configuration file not found at '{path}' (CONFIG_NOT_FOUND)."],
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

## Exception handling

`except Exception: pass` (or an equivalent silent `continue`) is not allowed
outside genuinely best-effort cleanup (e.g. discarding a partial sandbox after
a failed create). If the enclosing function already threads a
`warnings: list[str]` or `errors: list[str]` through its `Result`/`Outcome`
model — most do, per the pattern above — route the exception message into
that list instead of discarding it; the caller and the CLI renderer already
know how to surface it. If a broad `except` really is best-effort and nothing
should be reported, leave a one-line comment at the `except` site saying so.

## Docstrings and imports

- Docstrings follow the Google convention, enforced by ruff's `D` rules
  (`[tool.ruff]` in [pyproject.toml](../../pyproject.toml)). `__init__.py` and
  `tests/*` are exempt.
- `getworktree` is registered as first-party for isort; keep local imports grouped
  accordingly and let `ruff format`/`ruff check --fix` handle ordering.
- Use `__all__` in package root `__init__.py` files when re-exporting internal symbols into a public subpackage surface (e.g. `core/db/__init__.py`). Omit `__all__` in leaf modules.
