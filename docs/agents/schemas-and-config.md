# Schemas and Config

## Versioned JSON Schemas

`getworktree/schemas/v1/config.json` and `v1/workflow.json` are the source of truth
for what a valid `.worktree/config.json` and workflow YAML file look like. Both are
validated through `SchemaValidator` ([getworktree/common/schema_validation.py](../../getworktree/common/schema_validation.py)),
a thin wrapper over `jsonschema.Draft202012Validator` that returns a
`ValidationResult(ok, errors)` instead of raising.

### Config V1 contract

`config.json` under `schemas/v1/` is the **only** structural source of truth for config V1
(draft 2020-12). Runtime validation uses packaged `CONFIG_VALIDATOR`; do not
duplicate the schema in Python.

Strictness:

- Root and every nested object use `additionalProperties: false` (unknown keys
  fail validation).
- Top-level `required`: `version`, `project`, `paths`, `sandbox`,
  `agent`, `history`, `doctor`, `prune`, `telemetry`.
- `version` is integer `const: 1`.

Enums (exact tokens):

- Config `agent.provider`: `local` | `ollama` | `cursor` | `gemini` |
  `copilot` | `openai` | `anthropic` | `azure_openai` | `custom` (runtime
  factory supports **`local`**, **`ollama`**, **`cursor`**, **`gemini`**, and
  **`copilot`**; other tokens remain schema-valid for future providers)
- Workflow `agent.provider` (`workflow_v1.json`): `local` | `ollama` | `cursor` |
  `gemini` | `copilot`

For `wt workflow run`, **workflow** `agent.provider` selects the adapter; **config**
`agent.model` / `endpoint` / `temperature` / `max_tokens` fill the request.
Ollama uses `config.agent.model` + `config.agent.endpoint` (or `OLLAMA_HOST`).
Cursor uses `config.agent.model` and `CURSOR_API_KEY`. Gemini uses
`GEMINI_API_KEY`. Copilot uses `GH_TOKEN` or `GITHUB_TOKEN`. Cursor, Gemini,
and Copilot mutate the sandbox directly through the shared base in
`core/workflows/agents/cli_mutation.py`; local and Ollama still return diffs.
Note: `wt workflow run` currently validates the workflow definition only —
step execution is not implemented yet (tracked in issues #171-#173).

Notable bounds / string rules:

- Path strings (`paths.*`, `sandbox.base_ref`): non-empty (`minLength: 1`)
- Positive integers (`minimum: 1`): `sandbox.max_active_sandboxes` /
  `default_timeout_seconds`, `agent.max_tokens`, `history.max_sessions`
- `agent.temperature`: number in `[0, 2]`
- `prune.artifact_ttl_days`: integer `minimum: 0`
- `agent.model` / `agent.endpoint`: `string | null`; non-null strings must be
  non-empty
- `project.name` / `project.initialized_at`: `string | null` (loader maps null
  name to `"unnamed_project"` after schema validation)

Not expressed in the JSON Schema (validator-engine / runtime territory):

- Path validity (e.g. NUL/newline characters in `paths.*` values)
- Filesystem existence or writability of path values
- Provider-specific required `model` / `endpoint`

Pydantic models in
[getworktree/core/config/models.py](../../getworktree/core/config/models.py)
mirror the same enums, bounds, and `extra: "forbid"`. Defaults live in
`CANONICAL_V1_DEFAULTS` and must remain schema-valid after generation.

## Config generation

`CANONICAL_V1_DEFAULTS` in [getworktree/core/config/generator.py](../../getworktree/core/config/generator.py)
is the single source of default values. `generate_default_config` has three modes:

- default (file missing): create from defaults.
- `--overwrite`: replace the file entirely with fresh defaults.
- `--repair`: non-destructively insert missing keys via `merge_missing_keys`,
  preserving existing user values (including `project.initialized_at`).

The loader never writes defaults to disk. Writers own defaults; readers only load
and classify.

## Config load API

All runtime reads of `.worktree/config.json` go through
[getworktree/core/config/loader.py](../../getworktree/core/config/loader.py).
Typed config lives in
[getworktree/core/config/models.py](../../getworktree/core/config/models.py).
Repo context/warnings live in
[getworktree/core/config/context.py](../../getworktree/core/config/context.py).
Command packages must not call `json.load` on config directly.

Default path: `get_worktree_config_file(cwd)` → `<repo>/.worktree/config.json`.
`resolve_config_path(cwd=..., config_path=...)` returns an absolute path;
explicit `config_path` wins when provided.

### Primary API

`load_config_result(cwd=None, *, config_path=None) -> ConfigLoadResult` is the
primary surface. It does not print, call `sys.exit`, or create/mutate files.

```python
class ConfigLoadStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    MALFORMED_JSON = "malformed_json"
    ROOT_NOT_OBJECT = "root_not_object"
    SCHEMA_INVALID = "schema_invalid"
    PATH_IS_DIRECTORY = "path_is_directory"
    UNREADABLE = "unreadable"


class ConfigLoadResult(BaseModel):
    status: ConfigLoadStatus
    config_path: Path  # absolute
    raw: dict[str, Any] | None
    config: WorktreeConfig | None
    errors: list[str]

    @property
    def ok(self) -> bool: ...  # status == OK
```

On success (`status=ok`): `raw` is the parsed object, `config` is a populated
`WorktreeConfig` (full V1 surface: version, project, paths, sandbox, agent,
history, doctor, prune, telemetry), and `errors` is empty.
`project.name` of `null` normalizes to `"unnamed_project"`.

### Error codes

Stable identifiers for tests and doctor checks (wording of full sentences may
change; codes should not):

| Code | Status |
|------|--------|
| `CONFIG_NOT_FOUND` | `not_found` |
| `CONFIG_MALFORMED_JSON` | `malformed_json` |
| `CONFIG_ROOT_NOT_OBJECT` | `root_not_object` |
| `CONFIG_SCHEMA_INVALID` | `schema_invalid` |
| `CONFIG_PATH_IS_DIRECTORY` | `path_is_directory` |
| `CONFIG_UNREADABLE` | `unreadable` |

Schema validation uses packaged `CONFIG_VALIDATOR` / `config_v1.json`. Non-object
roots skip schema validation (`root_not_object`).

### Raising helpers

Thin wrappers over the same internals (no print/exit):

- `load_raw_config(config_path) -> dict`
- `parse_and_validate_config(raw) -> WorktreeConfig`
- `load_config(cwd=None, *, config_path=None) -> WorktreeConfig`

They raise `FileNotFoundError` for `not_found`, `OSError` for `unreadable`, and
`ValueError` for other non-ok statuses, using messages from `errors`.

### Context warnings

`load_context` in `core/config/context.py` builds `WorktreeContext` (config +
current branch + warnings) via `load_config`. Warning policy (missing agent model,
primary branch, high sandbox limits) is separate from load classification.

## Config validate API

Validate-oriented reads go through
[getworktree/core/config/validate.py](../../getworktree/core/config/validate.py).
The engine reuses `load_config_result` for path resolution, IO/parse/schema
classification, and typed mapping, then applies semantic rules that are not
expressed in `config_v1.json`. It does not print, call `sys.exit`, or mutate
files.

### Primary API

`validate_config_result(cwd=None, *, config_path=None) -> ConfigValidationResult`
is the primary surface for `wt config validate` and later doctor/checks.

```python
class ConfigValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    MALFORMED_JSON = "malformed_json"
    ROOT_NOT_OBJECT = "root_not_object"
    PATH_IS_DIRECTORY = "path_is_directory"
    UNREADABLE = "unreadable"


class ConfigValidationResult(BaseModel):
    status: ConfigValidationStatus
    config_path: Path  # absolute
    raw: dict[str, Any] | None
    config: WorktreeConfig | None
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool: ...  # status == VALID
```

Path resolution matches the loader: default
`get_worktree_config_file(cwd)` → `<repo>/.worktree/config.json`; explicit
`config_path` wins. Result always carries an absolute `config_path`.

### Status mapping from load

| Load-style condition | Validation `status` |
|----------------------|---------------------|
| success after schema + map + no semantic errors | `valid` |
| schema / mapping failure, or semantic errors | `invalid` |
| missing file / missing parents | `not_found` |
| malformed JSON | `malformed_json` |
| root not object | `root_not_object` |
| path is directory | `path_is_directory` |
| unreadable | `unreadable` |

IO/parse failures preserve loader error message text and codes; `warnings` is
empty and `config` is `null`. Schema failures use the grouped
`CONFIG_SCHEMA_INVALID` block from the loader. On success, `config` is a
populated `WorktreeConfig`, `raw` is the parsed object, and `errors` is empty
(warnings may still be present). Semantic errors yield `status=invalid`,
`ok=false`, `config=null`, with non-empty `errors` (warnings may still be set).

### Error / warning codes

| Code | Kind | When |
|------|------|------|
| `CONFIG_NOT_FOUND` | error | missing config |
| `CONFIG_MALFORMED_JSON` | error | JSON parse failure |
| `CONFIG_ROOT_NOT_OBJECT` | error | root not object |
| `CONFIG_PATH_IS_DIRECTORY` | error | path is directory |
| `CONFIG_UNREADABLE` | error | read failure |
| `CONFIG_SCHEMA_INVALID` | error | schema or pydantic mapping failure |
| `CONFIG_SEMANTIC_PATH_INVALID` | error | any `paths.*` value has NUL/newline |
| `CONFIG_WARN_AGENT_MODEL_MISSING` | warning | non-`local` provider without model |
| `CONFIG_WARN_AGENT_ENDPOINT` | warning | non-null endpoint not absolute http(s) URL |
| `CONFIG_WARN_SANDBOX_LIMIT` | warning | `sandbox.max_active_sandboxes` > 10 |

Warnings never alone make `ok=false`. Ordering: IO/parse single error first;
else structural block; then semantic path errors (field order). Warnings
follow FR-7 rule order (model, endpoint, sandbox limit).

Commands must call this API rather than re-implementing schema or semantic
workflows.

## `wt config validate` CLI

Command entry: `getworktree.cli.config.command.config_validate_command`.
Registration: `wt config validate` under `config_app` in
[getworktree/cli.py](../../getworktree/cli.py).

The command is **read-only**: it never creates, repairs, overwrites, or deletes
config files. It calls `validate_config_result` only (no second schema/semantic
implementation in the command module). No `--path`, `--json`, or repair flags.

### Exit codes

| Condition | Exit code |
|-----------|-----------|
| `result.ok` (status `valid`), zero or more warnings | `0` |
| not ok (missing / malformed / schema / semantic / IO) | `1` |
| unexpected internal exception not converted by the engine | non-zero (must not silently exit `0`) |

Warnings never cause a non-zero exit by themselves.

### Success report (no warnings)

```text
Config: <absolute-path>
Status: valid

Config is valid.
```

`<absolute-path>` is `result.config_path` as an absolute POSIX path
(`Path.as_posix()`). No JSON dump of the config body.

### Success report (with warnings)

```text
Config: <absolute-path>
Status: valid with warnings

Warnings:
- <warning 1>
- <warning 2>

Config is valid.
```

Warning bullets are `result.warnings` in engine order. Multi-line entries keep
the first line on the bullet; continuation lines are indented by two spaces.
Trailing line is always exactly `Config is valid.` on ok paths.

### Failure report

- Exit `1`
- Rich error panel titled exactly `Config Validation Failed`
- Panel body is `"\n\n".join(result.errors)`, or fallback
  `Configuration validation failed.` when `errors` is empty
- No success header (`Config:` / `Status: valid`) and no `Config is valid.`
- If `warnings` is non-empty on an invalid result, print them after the panel on
  stdout as a `Warnings:` bullet list (same bullet formatting as success)

## Config serialization and `wt config show`

Runtime display of configuration uses the full V1 surface after model defaults
and load normalizations (not a sparse dump of on-disk keys).

Helpers in
[getworktree/core/config/serialize.py](../../getworktree/core/config/serialize.py):

- `serialize_config(config: WorktreeConfig) -> dict` — plain dict, no I/O, no
  print/exit; top-level key order is
  `version`, `project`, `paths`, `sandbox`, `agent`, `history`, `doctor`,
  `prune`, `telemetry`. Nested keys follow the
  Pydantic model / `CANONICAL_V1_DEFAULTS` field order.
- `as_json(config) -> str` — pretty JSON (`indent=2`, `ensure_ascii=False`) with
  a trailing newline. Parseable by `json.loads`.

`project.name` is never JSON `null` in serialized output (load maps null to
`"unnamed_project"`). Optional unset strings (`agent.model`, `agent.endpoint`,
`project.initialized_at`) serialize as JSON `null`.

### CLI success layout (`wt config show`)

`wt config show` loads via `load_config_result`. On success (`status=ok`, exit
`0`) stdout is exactly:

1. Source-metadata header (fixed labels, this order):
   - `Config: <absolute-path>` — `ConfigLoadResult.config_path` as an absolute
     path string
   - `Status: valid` — only for the success path
2. One blank line
3. Effective config JSON from `as_json(result.config)` (pretty JSON, trailing
   newline; no Rich markup/highlight)

Split success stdout on the first blank line: first block is the header,
remainder is parseable with `json.loads`.

On non-ok load it prints `ConfigLoadResult.errors` (error panel) and exits `1`
with **no** success header and **no** partial JSON. Show never creates or
mutates config files.

Command entry: `getworktree.cli.config.command.config_show_command`.

## Config set API and `wt config set`

Dot-path mutation lives in
[getworktree/core/config/mutate.py](../../getworktree/core/config/mutate.py).
This layer owns in-memory nested assignment and the persist path for
`wt config set`. It does **not** print, call `sys.exit`, or implement unset
(issue `#15`). CLI typed values are parsed by `parse_config_value`, and schema
key allow-lists / V1 schema validation are enforced before persisting.

### Pure helper

`set_nested_value(config_dict, dot_path, value) -> None` mutates
`config_dict` in place:

- Split `dot_path` on `.`
- Create missing intermediate segments as `{}`
- Raise `ValueError` on empty path / empty segment, or when an intermediate
  segment exists but is not a dict (scalar collision)

### Primary API

`set_config_value_result(key, value, *, cwd=None, config_path=None) -> ConfigSetResult`
loads raw JSON from disk (not via schema-validated `load_config_result`, so
already-invalid files can still be patched), deep-copies, applies
`set_nested_value`, validates the resulting object against the V1 JSON schema
and `WorktreeConfig` model, and writes with `atomic_write_json` only on success.

```python
class ConfigSetStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    MALFORMED_JSON = "malformed_json"
    ROOT_NOT_OBJECT = "root_not_object"
    SCHEMA_INVALID = "schema_invalid"
    PATH_IS_DIRECTORY = "path_is_directory"
    UNREADABLE = "unreadable"
    TYPE_COLLISION = "type_collision"
    INVALID_PATH = "invalid_path"
    WRITE_FAILED = "write_failed"


class ConfigSetResult(BaseModel):
    status: ConfigSetStatus
    config_path: Path  # absolute
    key: str
    value: Any = None
    errors: list[str]

    @property
    def ok(self) -> bool: ...  # status == OK
```

Path resolution matches the loader (`resolve_config_path`). On type collision,
schema validation error, or invalid path, the on-disk file is left unchanged.

### Error codes

| Code / condition | Status |
|------------------|--------|
| `CONFIG_NOT_FOUND` | `not_found` |
| `CONFIG_MALFORMED_JSON` | `malformed_json` |
| `CONFIG_ROOT_NOT_OBJECT` | `root_not_object` |
| `CONFIG_SCHEMA_INVALID` | `schema_invalid` |
| `CONFIG_PATH_IS_DIRECTORY` | `path_is_directory` |
| `CONFIG_UNREADABLE` | `unreadable` |
| `CONFIG_WRITE_FAILED` | `write_failed` |
| scalar intermediate collision message | `type_collision` |
| empty / empty-segment path message | `invalid_path` |

### CLI (`wt config set`)

Command entry: `getworktree.cli.config.command.config_set_command`.
Registration: `wt config set <key> <value>` under `config_app` in
[getworktree/cli.py](../../getworktree/cli.py).

| Condition | Exit | Output |
|-----------|------|--------|
| success | `0` | green success: `Config updated: <key> = <value>` |
| any non-ok result | `1` | red panel **Config Error** with `"\n\n".join(result.errors)` |

## Workflow blueprint resolution

Workflow blueprints are catalog items: discovery, YAML parsing, schema
validation, and name resolution all flow through the catalog layer's
`get_catalog_item(name, CatalogItemType.WORKFLOW, definition_cls=WorkflowDefinition, cwd=root)`
(`getworktree.core.catalog.services.inventory`) — the same surface used by
`wt task` and `wt step`. `WorkflowDefinition` (in
[getworktree/core/workflows/models.py](../../getworktree/core/workflows/models.py))
declares a `schema_validator: ClassVar[SchemaValidator]` bound to
`WORKFLOW_VALIDATOR`, which the catalog's internal `_validate_definition` helper
detects automatically and runs against the parsed YAML before constructing the
model. There is no separate workflow discovery/inventory/resolve/validate
pipeline; a non-ok `DefinitionResolutionResult` carries schema or lookup errors
in `result.errors`, formatted for CLI panels by
`format_workflow_run_resolve_failure` in
[getworktree/core/workflows/services/renderer.py](../../getworktree/core/workflows/services/renderer.py).

## Task blueprint resolution & execution

Task blueprints live under `.worktree/catalog/tasks/` and resolve through the
same catalog inventory path as workflows.

### `TaskDefinition`

Model: [getworktree/core/task/models.py](../../getworktree/core/task/models.py)

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | Required |
| `description` | `str` | Default `""` |
| `summary` | `str` | Default `""` |
| `use_sandbox` | `bool` | Default `True` |
| `steps` | `list[StepDefinition]` | Default `[]` |

Before validation, `_fill_step_shorthand_defaults` normalizes each raw step dict:

- Missing/empty `id` → slug from `name`, else `step-{idx}` (1-based).
- Bare `command: ...` with no `run` / `uses` / `type` → mapped to `run`.

Example:

```yaml
name: lint-fix
description: Run project linters
use_sandbox: true
steps:
  - command: ruff check .
  - id: tests
    name: unit tests
    run: pytest -q
```

Exceptions subclass the shared definition bases in
[getworktree/common/exceptions.py](../../getworktree/common/exceptions.py):

- `TaskLoadError(DefinitionLoadError)`
- `TaskValidationError(DefinitionValidationError)`

### Resolve: `resolve_and_load_task`

[getworktree/core/task/services/loader.py](../../getworktree/core/task/services/loader.py)

```python
def resolve_and_load_task(
    name: str,
    cwd: Path | None = None,
) -> DefinitionResolutionResult[CatalogRecord]:
    return get_catalog_item(
        name,
        CatalogItemType.TASK,
        definition_cls=TaskDefinition,
        cwd=cwd,
    )
```

Thin catalog wrapper only — no custom YAML scan/parse pipeline. On success,
`result.definition` is a `TaskDefinition`. Failure bodies for CLI panels come
from `format_task_resolve_failure` in
[getworktree/core/task/services/renderer.py](../../getworktree/core/task/services/renderer.py).

### Execute: `run_task`

[getworktree/core/task/services/runner.py](../../getworktree/core/task/services/runner.py)

```python
def run_task(
    definition: TaskDefinition,
    cwd: Path,
    *,
    use_sandbox: bool = True,
    keep: bool = False,
    agent: str | None = None,
    observer: RunObserver | None = None,
) -> RunOutcome: ...
```

Builds a `RunContext` (`steps=definition.steps`,
`use_sandbox=use_sandbox and definition.use_sandbox`, plus `keep` / `agent` /
`observer`) and delegates to `run_steps`. CLI orchestration
(`resolve` → insert RUNNING row → `run_task` → update status → render) lives in
[getworktree/cli/task/command.py](../../getworktree/cli/task/command.py); Rich
output is in `cli/task/renderers.py`, plain failure text in
`core/task/services/renderer.py` (`format_task_run_failure`).

## Shared step execution layer (`core/runtime/`)

Package: [getworktree/core/runtime/](../../getworktree/core/runtime/)
(`models.py`, `engine.py`). Used by `run_task` today; workflow multi-step
execution should reuse the same surface when implemented.

### `RunContext`

Immutable dataclass inputs:

| Field | Type | Default |
|-------|------|---------|
| `steps` | `list[StepDefinition]` | required |
| `cwd` | `Path` | required |
| `use_sandbox` | `bool` | `True` |
| `keep` | `bool` | `False` |
| `agent` | `str \| None` | `None` |
| `observer` | `RunObserver \| None` | `None` |

### `RunObserver`

Optional protocol hooks (no-ops when `observer is None`):

- `on_sandbox_ready(path: Path, active: bool)`
- `on_step_start(idx: int, total: int, step: StepDefinition)`
- `on_step_done(idx: int, total: int, result: StepResult)`
- `on_sandbox_cleanup(kept: bool, path: Path)`

`cli/task/command.py` implements `CliRunObserver` against `RichOutput`.

### `RunOutcome`

Pydantic model (`extra=forbid`, `strict=True`):

| Field | Type | Notes |
|-------|------|-------|
| `status` | `RunStatus` | `running` / `completed` / `failed` / `cancelled` |
| `step_results` | `list[StepResult]` | default `[]` |
| `error_message` | `str \| None` | setup failure, first failed step, or cancel |
| `sandbox_kept` | `bool` | default `False` |
| `sandbox_path` | `Path` | sandbox path or resolved cwd |

`ok` is true when `status == RunStatus.COMPLETED`.

### `run_steps(context) -> RunOutcome`

Flow in [getworktree/core/runtime/engine.py](../../getworktree/core/runtime/engine.py):

1. **Sandbox setup** (`_setup_sandbox`): if `use_sandbox` is false, execute in
   `cwd` and notify `on_sandbox_ready(..., active=False)`. Otherwise
   `GitSandboxManager.create_sandbox_result()`; setup failure returns
   `status=failed` with `error_message` and no steps run.
2. **Step loop** (`_run_step_loop`): for each step, notify start, call
   `execute_step(step, sandbox_path=target_dir, context=agent_context)`, notify
   done. First non-ok `StepResult` stops the loop with `status=failed`.
   `KeyboardInterrupt` → `status=cancelled`.
3. **Cleanup** (always in `finally`): unless `keep` is true, best-effort
   `cleanup_sandbox`; notify `on_sandbox_cleanup`.

Domain packages must not re-implement this loop or sandbox lifecycle.

## Catalog templates & seeding

Packaged scaffolds live under
[getworktree/core/catalog/templates/](../../getworktree/core/catalog/templates/)
(`workflows/`, `tasks/`, `steps/`), including `default.yml` per type and curated
`wt/` seed trees. Path helper: `get_catalog_templates_dir()` in
[getworktree/common/fs.py](../../getworktree/common/fs.py).

Curated step seeds ship under `templates/steps/wt/`
(`git-sync-base`, `ai-planner`, `ai-code-patcher`, `run-tests`, `ai-reviewer`)
and seed into `.worktree/catalog/steps/wt/`. Workflow seeds under
`templates/workflows/wt/` may reference them with `uses: wt/<name>` (for example
`wt/ai-code-patcher`).

Seeding ([getworktree/core/catalog/services/seeder.py](../../getworktree/core/catalog/services/seeder.py)):

- `seed_catalog_templates(item_type, cwd=None, *, force=False) -> SeedResult` —
  copies packaged `wt/` files into
  `.worktree/catalog/<type>s/wt/` (skips existing files unless `force`).
- `seed_all_catalog_templates(cwd=None, *, force=False) -> SeedResult` —
  seeds `workflow`, `task`, and `step` and aggregates `SeedResult`.


CLI template surfaces (no separate `wt template` command group):

- `wt catalog list --type template` — lists packaged `default.yml` scaffolds
  (type + relative path table).
- `wt catalog show <name>` — after a local catalog miss, falls back to packaged
  templates matching the name and prints raw YAML via
  `render_template_show_content`.

## `wt workflow list`

Command entry: `getworktree.cli.workflow.command.workflow_list_command`.
Registration: `wt workflow list` (and `wt workflow`) under `workflow_app` in
[getworktree/cli.py](../../getworktree/cli.py).

Read-only: query recorded workflow sessions, print a human-readable
Rich table `Recorded Workflows` or `No recorded workflows found.` empty state.

### Exit codes

| Condition | Exit |
|-----------|------|
| list ok (empty or recorded sessions) | `0` |
| uninitialized worktree or config load error | `1` |

## `wt workflow show`

Command entry: `getworktree.cli.workflow.command.workflow_show_command`.
Registration: `wt workflow show` under `workflow_app` in
[getworktree/cli.py](../../getworktree/cli.py).

Read-only: query a recorded workflow session by session ID and print details
(session id, name, branch, status, timestamps, error). Workflow *definition*
display is handled by `wt catalog show`, not this command.

### Exit codes

| Condition | Exit |
|-----------|------|
| session found | `0` |
| uninitialized worktree, config load error, or session not found | `1` |

## `wt workflow run` error bodies

Pure formatters (no IO/print/exit) for resolve/validate failure panel bodies live in
[getworktree/core/workflows/services/renderer.py](../../getworktree/core/workflows/services/renderer.py):

- `format_workflow_run_resolve_failure(result: DefinitionResolutionResult[CatalogRecord]) -> str`
- `format_workflow_run_validate_failure(result: DefinitionValidationOutcome) -> str`

Resolve body: `"\n\n".join(errors)` or `Failed to resolve workflow.`
Validate body: `"\n\n".join(errors)` or `Workflow definition is invalid.`

## Changing config or workflow shape

1. Update the relevant JSON Schema (`config_v1.json` or `workflow_v1.json`).
2. Update `CANONICAL_V1_DEFAULTS` (config) or the packaged templates under
   `core/catalog/templates/` (workflows/tasks/steps `default.yml` and curated
   `wt/` seeds). See **Catalog templates & seeding** above for list/show fallback.
3. Update the corresponding Pydantic model (`core/config/models.py`,
   `core/workflows/models.py`, or `core/task/models.py` as applicable).
4. Add/adjust tests under the matching `tests/core/...` package.

Bump the schema version (`config_v2.json`, etc.) instead of making breaking
changes to a `v1` schema that users may already have on disk.

## Step Definition Schema and Execution Engine

Step primitives stored in `.worktree/catalog/steps/` represent reusable blueprints shared by
catalog steps, workflow steps, and task steps. Models and engine live in
[getworktree/core/step/](../../getworktree/core/step/).

### `FailurePolicy` and `FailureSpec`

`FailurePolicy` (`getworktree/core/step/models.py`) is a `StrEnum`: `abort`, `continue`,
`prompt_user`, `retry`. `FailurePolicy.context("terminal")` returns `{abort, continue,
prompt_user}` (excludes `retry`); any other name returns the full set.

`FailureSpec` is the normalized `on_failure` directive (`extra: forbid`):

- `action`: FailurePolicy (required)
- `max_retries`: int (default `3`, `>= 1`)
- `backoff_ms`: int (default `0`, `>= 0`)
- `on_max_retries`: FailurePolicy (default `abort`; must be in `FailurePolicy.context("terminal")`)

### StepDefinition Model

`StepDefinition` uses `model_config = {"extra": "forbid", "strict": True, "populate_by_name": True}`
and is the single model for catalog step blueprints, workflow steps, and task steps:

- `id`: str (required, unique step identifier)
- `uses`: str | null (reference to another step by id/name)
- `run`: str | null (shorthand for a `type=command` step)
- `name`: str | null
- `type`: StepType | null (`command`, `agent`, `script`)
- `description`: str | null
- `command`: str | null (required if `type == "command"`)
- `prompt`: str | null (required if `type == "agent"`)
- `script_path`: str | null (relative path, required if `type == "script"`)
- `tools`: list[str] (tool permission strings, default `[]`)
- `env`: dict[str, str] (default `{}`)
- `timeout_seconds`: int (default `120`, must be > 0)
- `assert_`: StepAssert | null (aliased to `assert`)
- `on_failure`: FailureSpec (default `FailureSpec(action=abort)`; accepts a bare policy string or a full object)

A step-shape validator enforces exactly one of `run` / `uses` / inline `type`:

- `run` cannot be combined with `uses`, `command`, `type`, `prompt`, `script_path`, or `tools`.
- Inline `type=command` requires `command`; `type=agent` requires `prompt`; `type=script`
  requires `script_path`.
- If none of `run`, `uses`, or `type` is set, validation fails.

`StepDefinition` does not support a `with`/override mechanism in v1 — `uses` steps load the
referenced step definition as-is.

### `LoopStepBlock`

`LoopStepBlock` also lives in `core/step/models.py`: `id`, `type: Literal["loop"]`,
`max_iterations` (default `5`), `until` (non-empty list), `do` (non-empty list of
`StepDefinition`), and `on_max_iterations: FailurePolicy` (default `prompt_user`, restricted to
`FailurePolicy.context("terminal")` — a value of `retry` raises a validation error).

### Step Loader & Resolver

- `load_step_definition(path: Path) -> StepDefinition`: Loads and parses a step YAML file. Raises `StepNotFoundError` if file missing/unreadable, `StepValidationError` on YAML or Pydantic validation error.
- `load_step_by_id(step_id_or_name: str, cwd: Path | None = None) -> StepDefinition`: Resolves from `.worktree/catalog/steps/` only (local catalog after seed; no package-resource bypass at runtime). Direct path first: `wt/<name>` → `.worktree/catalog/steps/wt/<name>.yml` (also `.yaml`); unprefixed `<name>` → `.worktree/catalog/steps/<name>.yml`. If no direct file, scan YAML under the steps tree including `wt/` for matching `id`/`name` (invalid siblings skipped during scan). Missing directory or no match → `StepNotFoundError`.
- `resolve_step_definition(step: StepDefinition, *, cwd: Path | None = None) -> StepDefinition`: Normalizes a step with `uses` (loads the referenced step via `load_step_by_id()`, including `uses: wt/<name>`) or `run` (synthesizes `type=command`, `command=run`) into a concrete, directly executable `StepDefinition`. Inline `type` steps pass through unchanged.

### Step Execution Engine

`execute_step(step: StepDefinition, sandbox_path: Path, context: dict | None = None) -> StepResult`:

- Resolves `uses`/`run` steps via `resolve_step_definition()` before dispatch.
- Executes the step primitive inside `sandbox_path` with isolated working directory `cwd=sandbox_path`.
- Enforces process timeouts via `timeout_seconds`.
- Handles `on_failure` policies:
  - `action == "retry"`: retries execution up to `max_retries` attempts, sleeping `backoff_ms` milliseconds between attempts. After the final failed attempt, evaluates `on_max_retries`: `continue` returns `status="ignored"` (`ok=True`); `abort`/`prompt_user` return `status="failed"`.
  - `action == "continue"` (no retry): a single failed attempt returns `status="ignored"` (`ok=True`).
  - `action == "abort"` / `"prompt_user"` (no retry): a single failed attempt returns `status="failed"`. There is no interactive `prompt_user` UI yet, so it behaves like `abort`.
- Returns `StepResult`: `step_id`, `status` (`completed`, `failed`, `ignored`), `exit_code`, `stdout`, `stderr`, `duration_seconds`, `attempts`, `error_message`. `@property def ok` returns `True` for `completed` or `ignored`.

