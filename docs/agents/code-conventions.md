# Code Conventions

Coding standards and patterns for the Worktree CLI codebase.

---

## Pydantic Models

**Relevant sources:** `src/worktree/core/*/models.py`, `src/worktree/common/models.py`

- Every Result, Outcome, and DTO model must specify:
  ```python
  model_config = {"extra": "forbid", "strict": True}
  ```
- Catches typos in constructed payloads and unexpected extra keys early.
- Scoped exceptions (must carry a justifying comment):
  - `OllamaModelStdout` (`core/agents/ollama.py`): leniency for LLM-generated JSON.
  - `BlueprintDefinition`, `BlueprintDefaults`, `LoopStepBlock` (`core/blueprint/models.py`, `core/step/models.py`): hand-authored YAML models using `extra: "ignore"`.

---

## Variable Naming

- Prefer clear, self-explanatory names over arbitrary abbreviations.
- **Acceptable**: Standard conventions (`exc`, `rel_path`, `i`/`v` in comprehensions, `fs`, `cwd`, `db`).
- **Unacceptable**: Cryptic truncations (e.g. `val_res` -> `validation_result`, `err_msg` -> `error_message`, `res` -> `result`).

---

## Structure and Complexity

**Relevant sources:** `pyproject.toml`, `tasks.py`

- Functions/classes with > 5 arguments should accept an environment/context/configuration object (frozen dataclass).
- Avoid God-functions; decompose complex workflows into focused helpers.
- Function complexity threshold: **Cognitive complexity <= 10** enforced by `complexipy` (`inv complexity`).
- Do not add test seams to production function or class signatures.

### Blank Lines in Function Bodies
- Separate distinct logical phases (setup, validate, persist, return) with a blank line.
- Keep cohesive, tightly coupled lines together.

### Assertions
- Use `assert` **only in tests**.
- Production code must raise domain exceptions or return structured Result/Outcome error objects.

---

## Core Package Layout

**Relevant sources:** `src/worktree/core/`

Standard package skeleton for domain logic:

```text
core/<domain>/
  __init__.py       # Re-export public API only
  models.py         # BaseModel, StrEnum, dataclasses, Protocols
  exceptions.py     # Domain exceptions
  facade.py         # Domain facade class (if applicable)
  services/         # Imperative operations
    <verb>.py       # loader, runner, renderer, resolver, etc.
```

- **Must:** Put new domain types in `models.py` and imperative operations in `services/<verb>.py`.
- **Must not:** Add logic directly under package roots (except documented entrypoints), define public models in `services/`, or extend legacy flat layouts.

---

## Result/Outcome Pattern

**Relevant sources:** `src/worktree/common/models.py`, `src/worktree/core/*/models.py`

Operations that can fail return a Pydantic result object subclassing `BaseResult` instead of raising:
- `status: StrEnum`: Outcome state.
- `warnings: list[str]`: Non-fatal issues (inherited from `BaseResult`).
- `errors: list[str]`: Fatal issues (inherited from `BaseResult`).
- `fixes: list[str]`: Suggested fixes or remediations (inherited from `BaseResult`).
- `ok: bool`: Property returning `not bool(self.errors)` or `status == OK`.
- Callers check `.ok` and render `.errors` / `.warnings` rather than catching exceptions.

---

## Atomic File Writes

**Relevant sources:** `src/worktree/common/filesystem/services/operations.py`, `src/worktree/common/filesystem/facade.py`

- Never write config or state files directly in-place.
- Write to a `.tmp` sibling, flush, `os.fsync`, and atomically swap via `Path.replace`.
- Use `Filesystem.atomic_write_json` and `Filesystem.atomic_write_text`.

---

## Console Output and Terminal Formatting
 
**Relevant sources:** `src/worktree/cli/ui/`
 
- Terminal output must route through `ui_dispatcher.dispatch(result)` — direct `print()`, `rich` imports, `typer.echo`, and console output outside `src/worktree/cli/ui/dispatcher.py` are strictly banned by Ruff lint rules (`T20`, `TID251`) and AST tests.
- Formatters reside under `src/worktree/cli/ui/formatters/<domain>/<name>.py`, strictly one `*Formatter` class per module.
- Domain shared table builders reside in `src/worktree/cli/ui/formatters/<domain>/common.py`.
- No `renderers.py` modules exist anywhere in the codebase.
- Construct `errors` and `warnings` messages using inline f-strings or literals at call sites. Do not create private single-message formatting wrappers.

---

## Docstrings and Imports

**Relevant sources:** `pyproject.toml`

- Docstrings follow the Google convention (enforced by Ruff `D` rules).
- Use absolute imports (`worktree.*`) across packages. Relative imports are allowed only within the same directory (`from . import ...`).
- Use `__all__` in package `__init__.py` files when re-exporting internal symbols into a public subpackage surface.
