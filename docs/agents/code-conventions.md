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
 
- Terminal output must route through `ui_dispatcher.dispatch(result)`. Direct
  `print()`, `rich` imports, `typer.echo`, and console writes belong only in
  `src/worktree/cli/ui/`. Ruff (`T20`, `TID251`) and the AST suite enforce
  parts of this; they currently exempt only `dispatcher.py` and do not detect
  `console.print`, `input`, or `typer.confirm`.
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
- **Top-level imports**: Always place imports at the top of the module across both production code and test suites. Do **not** use inline imports inside functions, methods, or test cases unless strictly necessary to break circular dependencies or avoid expensive eager initialization (any scoped inline import must carry a justifying comment).

---

## Type Annotations and `Any`

**Relevant sources:** `pyproject.toml` (`[tool.basedpyright]`)

`typeCheckingMode = "recommended"` reports every `Any` as a warning
(`reportAny`, `reportExplicitAny`). Warnings do not fail
`basedpyright src --level error`, so acting on them is a judgement call, and
this is the basis for that judgement.

**Parameters and returns are not equivalent.** `Any` on a parameter loses
checking inside one function. `Any` on a return type loses it at every call
site, transitively. Treat `-> Any` as a defect unless the value is genuinely
unconstrained.

**Prefer `object` over `Any`** when a value is only stored, compared, or passed
through. `object` forces a narrow before use; `Any` forces nothing.

### Permitted, do not "fix" these

1. **Pydantic `mode="before"` validator signatures.** A pre-validator receives
   whatever the user wrote in `config.json` or a blueprint YAML, so
   `(cls, val: Any) -> Any` is the contract. See `core/step/models.py`,
   `core/inputs/models.py`, `core/blueprint/models.py`.
2. **`dict[str, Any]` at a serialization boundary.** The result of
   `model_dump(mode="json")`, parsed YAML, or a JSON payload.
3. **Values read out of a user document and then compared.**
   `core/step/services/conditions.py` evaluates `until:` expressions against
   arbitrary JSON. Use `object` where only equality or truthiness is needed;
   keep `Any` where the value is indexed or used arithmetically.
4. **`**kwargs: Any` on a pass-through wrapper** that does not inspect the
   values.

### Banned

1. **`Any` that dodges an import boundary.** An annotation that exists because
   the real type cannot be imported from the current package is a symptom of
   misplaced code. Move the code, then name the type.
2. **`Any` as a test seam.** An `output: Any = None` parameter that production
   never reads exists only so a test can pass a stub. Delete the parameter; see
   "No test seams in production code" in [testing.md](testing.md).
3. **`Any` where a model already exists.** `step: Any` or `metadata: Any` when
   `StepDefinition` is right there. Same defect as a
   `getattr(obj, "field", "unknown")` chain: it moves a type error to runtime
   and defaults it to a wrong value.
4. **`Any` in a third-party override.** `def invoke(self, ctx: Any) -> Any`
   overriding a Click method should name `click.Context`.
5. **`Any` filling a generic you did not want to think about.**
   `subprocess.Popen[Any]` should be `Popen[bytes]` or `Popen[str]`; the code
   already knows which.

### Rule of thumb

If you cannot say in one sentence what values can arrive, `Any` is honest. If
you can, name them.

---

## Type Checker Suppressions

**Relevant sources:** `pyproject.toml` (`[tool.basedpyright]`)

`basedpyright` honors only `# pyright: ignore[reportRuleName]`. A
`# type: ignore` or `# type: ignore[code]` is a silent no-op: it looks
acknowledged and suppresses nothing. Three of those no-ops already exist
(`multiprocessing.Queue` in `tests/core/test_concurrent_sandbox.py` and
`tests/common/test_lock.py`, and `# type: ignore[arg-type]` in
`tests/core/blueprint/test_blueprint_models.py`); delete or convert them
when those files are next opened, do not copy them.

**Default: fix the type.** An ignore is a last resort, never a way to green
`basedpyright --level error`. `cast(...)` is not an alternative: it lies to
the checker and, when the target is `Any`, infects every use of the value.

### Permitted, do not "fix" these

1. **Intentional ill-typed test inputs** whose subject is a runtime
   `TypeError` or `ValidationError`. `Step.load(123)` raising is the contract;
   the checker is correctly complaining. Prefer `Model.model_validate({...})`
   when that exercises the same path (Pydantic extra-field tests), because it
   needs no suppression. Keep the ignore when the call itself is the subject.
2. **Third-party stub conflicts** that our code cannot name correctly.
   SQLModel's `__tablename__: ClassVar[str]` versus SQLAlchemy's mapped type
   (`reportIncompatibleVariableOverride` in `core/db/models.py`) is the
   current instance.
3. **Platform-gated imports.** `msvcrt` does not exist when
   `pythonPlatform = "Linux"` (`reportMissingImports`,
   `reportConstantRedefinition` in `common/lock.py`).

Every permitted ignore carries a one-line reason naming which of the three
applies.

### Banned

1. **Any ignore that hides a type we can write.** `_fs: Filesystem = None`
   (`reportAssignmentType` in `core/config/facade.py`) is the teaching case:
   the annotation is lying, and the ignore is what keeps the lie compiling.
2. **`reportCallIssue` / `reportArgumentType` used to silence a sloppy test.**
   If the checker rejects a `MagicMock`, a wrong-shaped dict, or a missing
   generic argument, the fixture is the defect. `multiprocessing.Queue`
   becomes `Queue[dict[str, object]]`, not an ignore.
3. **`reportIncompatibleVariableOverride` except the SQLModel `__tablename__`
   stub.** A subclass that does not match its parent is a design bug.
4. **An ignore with no reason.**

### Rule of thumb

If the line is ill-typed on purpose, ignore with a reason. If it is ill-typed
by accident, fix it. If you cannot tell, it is an accident.

---

## Encapsulation and Private Members

- **Forbid private member access in production code**: Never access private attributes or methods (names with a leading underscore `_`) across module or class boundaries in `src/`.
- **Forbid importing private methods/functions**: Never import private functions, methods, or variables across modules in production code (`src/`).
- **Expose query properties**: Expose public boolean query properties (e.g. `is_interactive`, `is_terminal_format`, `is_enabled`, `has_*`) on classes rather than referencing private members from external callers.
- **Tests exemption**: Tests under `tests/` may assert against or inspect private members when strictly necessary to verify low-level internal implementation behavior.

---

## Backwards Compatibility

- Maintain backwards compatibility **only** for surfaces users interact with directly:
  - CLI commands, subcommands, arguments, and flags (e.g. renaming a sub-command).
  - Configuration files and blueprint YAML definitions (e.g. keys or values in `config.json`).
  - Stable machine-readable CLI output formats (e.g. JSON output event envelopes).
- Do **not** preserve backwards compatibility aliases, compatibility properties, or shim layers for internal code (`common/`, `core/`, or internal `cli/` modules) when refactoring or renaming symbols (e.g., do not keep `_unlock_fd` when renaming to `_unlock_file_descriptor`, or property aliases like `_fd`). Refactor internal callers and tests directly.
- **When in doubt**: Ask the user before introducing compatibility layers or deprecation shims for ambiguous boundaries.
