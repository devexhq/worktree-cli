# Schemas and Config

This doc favors pointers to source over duplicated field lists: anything you can get
correct and current from one `Read` of a model file (field names, types, defaults) is
not restated here. What *is* here is behavior assembled across multiple files that a
single file read won't give you: resolution order, status/error-code contracts, exact
CLI output shape, and validator interactions. See
[AGENTS.md](../../AGENTS.md#documentation) for why this doc is structured this way.

## Versioned JSON Schemas

`src/worktree/schemas/v1/config.json` and `v1/workflow.json` are the source of truth
for what a valid `.worktree/config.json` and workflow YAML file look like. Both are
validated through `SchemaValidator` ([src/worktree/common/schema_validation.py](../../src/worktree/common/schema_validation.py)),
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
  **`copilot`**; other tokens remain schema-valid for future providers — a
  config using one of them passes `wt config validate` but must fail with a
  clear, typed error the moment `get_agent_adapter` is asked to resolve it,
  not a bare `ValueError` surfacing mid-run; see
  [architecture.md](architecture.md#domain-ownership))
- Workflow `agent.provider` (`v1/workflow.json`): `local` | `ollama` | `cursor` |
  `gemini` | `copilot`

For blueprint execution (`wt run`), **workflow** `agent.provider` selects the adapter; **config**
`agent.model` / `endpoint` / `temperature` / `max_tokens` fill the request.
Ollama uses `config.agent.model` + `config.agent.endpoint` (or `OLLAMA_HOST`).
Cursor uses `config.agent.model` and `CURSOR_API_KEY`. Gemini uses
`GEMINI_API_KEY`. Copilot uses `GH_TOKEN` or `GITHUB_TOKEN`. Cursor, Gemini,
and Copilot mutate the sandbox directly through the shared base in
`core/agents/cli_mutation.py`; local and Ollama still return diffs. See
[architecture.md](architecture.md#adding-a-new-agent-provider) for the recipe
when adding a sixth provider, and
[troubleshooting.md](troubleshooting.md) for what each provider's setup
failures look like.

Not expressed in the JSON Schema (validator-engine / runtime territory):

- Path validity (e.g. NUL/newline characters in `paths.*` values)
- Filesystem existence or writability of path values
- Provider-specific required `model` / `endpoint`

`core/config/models.py` mirrors the same enums, bounds, and `extra: "forbid"`.
Defaults live in `CANONICAL_V1_DEFAULTS` and must remain schema-valid after
generation.

## Config generation

`CANONICAL_V1_DEFAULTS` in [src/worktree/core/config/generator.py](../../src/worktree/core/config/generator.py)
is the single source of default values. `generate_default_config` has three modes:

- default (file missing): create from defaults.
- `--overwrite`: replace the file entirely with fresh defaults.
- `--repair`: non-destructively insert missing keys via `merge_missing_keys`,
  preserving existing user values (including `project.initialized_at`).

The loader never writes defaults to disk. Writers own defaults; readers only load
and classify. Outcome type: `ConfigGenerationResult` (`created` / `skipped_existing`
/ `repaired` / `overwritten` / `inserted_keys` / `warnings` / `errors`, `ok` when
`errors` is empty) — see the model in `generator.py` for the exact shape.

## Config load API

All runtime reads of `.worktree/config.json` go through
[src/worktree/core/config/loader.py](../../src/worktree/core/config/loader.py).
Typed config lives in
[src/worktree/core/config/models.py](../../src/worktree/core/config/models.py)
(`WorktreeConfig` and its nested `ProjectConfig` / `PathsConfig` / `SandboxConfig` /
`AgentConfig` / `HistoryConfig` / `DoctorConfig` / `PruneConfig` / `TelemetryConfig`
sections — read that file for the exact field list, all `extra: "forbid", strict: True`).
Repo context/warnings live in
[src/worktree/cli/status/context.py](../../src/worktree/cli/status/context.py).
Command packages must not call `json.load` on config directly.

Default path: `get_worktree_config_file(path)` → `<repo>/.worktree/config.json`.
`resolve_config_path(path=..., config_path=...)` returns an absolute path;
explicit `config_path` wins when provided.

### Primary API

`load_config_result(path=None, *, config_path=None) -> ConfigLoadResult` is the
primary surface. It does not print, call `sys.exit`, or create/mutate files.

`ConfigLoadResult` (`core/config/loader.py`, `extra: "forbid", strict: True`):
`status: ConfigLoadStatus`, `config_path: Path` (absolute), `raw: dict | None`,
`config: WorktreeConfig | None`, `errors: list[str]`, `ok` property (`status == OK`).

On success (`status=ok`): `raw` is the parsed object, `config` is a populated
`WorktreeConfig` (full V1 surface), and `errors` is empty.
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

Schema validation uses packaged `CONFIG_VALIDATOR` / `v1/config.json`. Non-object
roots skip schema validation (`root_not_object`).

### Raising helpers

Thin wrappers over the same internals (no print/exit):

- `load_raw_config(config_path) -> dict`
- `parse_and_validate_config(raw) -> WorktreeConfig`
- `load_config(path=None, *, config_path=None) -> WorktreeConfig`

They raise `FileNotFoundError` for `not_found`, `OSError` for `unreadable`, and
`ValueError` for other non-non-ok statuses, using messages from `errors`.

### Context warnings

`load_context` in `cli/status/context.py` builds `WorktreeContext` (config +
current branch + warnings) via `load_config`. Current warning rules, in order: missing
`agent.model`, active branch is `main`/`master`, `sandbox.max_active_sandboxes > 5`.
This is a separate, narrower rule set from `wt config validate`'s semantic warnings
below (different threshold for the sandbox limit — 5 here vs. 10 there — because one
is a "you're probably about to do something risky on this branch" nudge and the other
is a schema-adjacent config check; that's intentional, not drift).

## Config validate API

Validate-oriented reads go through
[src/worktree/core/config/validate.py](../../src/worktree/core/config/validate.py).
The engine reuses `load_config_result` for path resolution, IO/parse/schema
classification, and typed mapping, then applies semantic rules that are not
expressed in `v1/config.json`. It does not print, call `sys.exit`, or mutate
files.

### Primary API

`validate_config_result(cwd=None, *, config_path=None) -> ConfigValidationResult`
is the primary surface for `wt config validate` and later doctor/checks.

`ConfigValidationResult` (`core/config/validate.py`, `extra: "forbid", strict: True`):
`status: ConfigValidationStatus`, `config_path: Path` (absolute), `raw: dict | None`,
`config: WorktreeConfig | None`, `errors: list[str]`, `warnings: list[str]`, `ok`
property (`status == VALID`).

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
else structural block; then semantic path errors (field order, sorted by field name).
Warnings follow rule order (model, endpoint, sandbox limit).

Commands must call this API rather than re-implementing schema or semantic
workflows.

## `wt config validate` CLI

Command entry: `worktree.cli.config.command.config_validate_command`.
Registration: `wt config validate` under `config_app` in
[src/worktree/cli/cli.py](../../src/worktree/cli/cli.py).

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
[src/worktree/core/config/serialize.py](../../src/worktree/core/config/serialize.py):

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

Command entry: `worktree.cli.config.command.config_show_command`.

## Config set API and `wt config set`

Dot-path mutation lives in
[src/worktree/core/config/mutate.py](../../src/worktree/core/config/mutate.py).
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

`ConfigSetResult` (`core/config/mutate.py`, `extra: "forbid", strict: True`):
`status: ConfigSetStatus`, `config_path: Path` (absolute), `key: str`,
`value: Any = None`, `errors: list[str]`, `ok` property (`status == OK`).

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

Command entry: `worktree.cli.config.command.config_set_command`.
Registration: `wt config set <key> <value>` under `config_app` in
[src/worktree/cli/cli.py](../../src/worktree/cli/cli.py).

| Condition | Exit | Output |
|-----------|------|--------|
| success | `0` | green success: `Config updated: <key> = <value>` |
| any non-ok result | `1` | red panel **Config Error** with `"\n\n".join(result.errors)` |

## Unified blueprint execution (`core/blueprint/` + `core/engine/`)

**This is the live path.** `wt run` and `wt resume` go through
`BlueprintRunService`/`BlueprintResumeService` → `Engine` → `run_steps` — not
through `core/task/` or `core/workflows/`, which are older, CLI-unused packages
(see [architecture.md](architecture.md#layers) for why they still exist). The
**Task blueprint resolution & execution**, **Workflow blueprint resolution**, and
workflow half of **Pause, checkpoint, and resume** sections below describe those
legacy packages; read this section first for what actually runs.

- `BlueprintDefinition` ([src/worktree/core/blueprint/models.py](../../src/worktree/core/blueprint/models.py),
  `extra: "ignore", populate_by_name: True`) unifies `TaskDefinition` and
  `WorkflowDefinition` into one model. Read the model for the exact field list.
  Non-obvious: `kind: BlueprintKind` (`task` | `workflow`) is **injected** by
  `BlueprintDefinition.from_document(raw, kind=...)`, never read from the YAML —
  any authored `kind` key is dropped before validation. `id` defaults to `name`
  when omitted (same as `WorkflowDefinition`, but without that model's schema/model
  `required` mismatch, since `BlueprintDefinition` has no `schema_validator` at
  all). A `kind=task` document containing a `LoopStepBlock` step fails validation
  (`"kind=task cannot contain loop steps"`) — loop steps are workflow-only here,
  same as the split enforced structurally by `TaskDefinition.steps:
  list[StepDefinition]` (no loop variant) vs. `WorkflowDefinition.steps:
  list[StepDefinition | LoopStepBlock]`.
- `Blueprint` ([src/worktree/core/blueprint/services/blueprint.py](../../src/worktree/core/blueprint/services/blueprint.py))
  is the load/inspect handle: `Blueprint.load(name, catalog=None)` resolves a
  catalog task/workflow by name/SHA and infers `kind` from the catalog item type;
  `Blueprint.from_path(path)` infers `kind` from the nearest `tasks/`/`workflows/`
  ancestor directory instead. `.resolve_inputs(cli_args, *, overrides=None)`
  delegates to `core.inputs.resolve_inputs` against the wrapped document's
  `inputs` — see **Inputs and interpolation** above.
- `Engine` ([src/worktree/core/engine/engine.py](../../src/worktree/core/engine/engine.py))
  is the process handle: `Engine(cwd=None)`, `.run(blueprint, request=None) ->
  RunOutcome`, `.resume(session_id, *, blueprint=None, observer=None,
  failure_prompter=None, non_interactive=False) -> RunOutcome`. `RunRequest`
  (`core/engine/models.py`, frozen dataclass) is the caller-options struct:
  `inputs`, `cli_args`, `use_sandbox` (`None` defers to `blueprint.use_sandbox`),
  `keep`, `agent`, `session_id`, `observer`, `failure_prompter`,
  `non_interactive`. Non-obvious behavior `RunContext`/`RunOutcome` alone don't
  convey:
  - Inputs are resolved (`blueprint.resolve_inputs`) **before** the run row is
    inserted; a resolve failure raises `EngineInputError` and no `RunsRepository`
    row is ever created for that attempt.
  - `Engine.run` mints `session_id` as `req.session_id or
    f"{blueprint.kind.value}_{uuid4().hex[:8]}"` when the caller doesn't supply
    one.
  - **Both** `.run` and `.resume` reject any `LoopStepBlock` in the blueprint's
    steps outright (`EngineRuntimeError`, `"Engine.run/resume does not execute
    loop steps"`) — `Engine` only ever builds a flat `RunContext.steps:
    list[StepDefinition]`. Loop-step execution is not wired into the live path at
    all yet, independent of the `kind=task` restriction above (a `kind=workflow`
    blueprint with a loop step is schema/model-valid but cannot currently be run
    by `Engine`).
  - `Engine` always stamps `session_id` onto the returned `RunOutcome` via
    `model_copy` after `run_steps` returns — this is what makes
    `RunOutcome.session_id` non-`None` in practice, even though `run_steps` itself
    never sets it (see **`RunOutcome`** above).
  - DB persistence failures around the run row (`create`, `update_status`) are
    caught and appended to `RunOutcome.warnings` rather than raised — a failed
    `wt history` write does not fail the run.
- `ResumableRun` ([src/worktree/core/engine/resumable.py](../../src/worktree/core/engine/resumable.py))
  is the non-raising classifier `Engine.resume` uses internally:
  `ResumableRun.load(session_id, blueprint=None, cwd=None) -> ResumableRun` never
  raises; check `.is_resumable` before calling `.ready()`, which raises
  `EngineResumeError` when not resumable. `EngineResumeStatus` (`core/engine/models.py`)
  statuses: `ok`, `not_found`, `wrong_status`, `missing_sandbox`,
  `corrupt_checkpoint`, `failed` — this is the live-path equivalent of
  `WorkflowResumeStatus` below; the two enums are not the same type and are not
  kept in sync by anything other than convention (they happen to have identical
  members today).

## Workflow blueprint resolution

**[status: describes `core/workflows/`, unused by the live CLI — see
**Unified blueprint execution** above for `wt run`/`wt resume`'s actual model
(`BlueprintDefinition`) and services (`Blueprint`, `Engine`).]**

Workflow blueprints are catalog items: discovery, YAML parsing, schema
validation, and name resolution all flow through the catalog layer's
`get_catalog_item(name, CatalogItemType.WORKFLOW, definition_cls=WorkflowDefinition, cwd=root)`
(`worktree.core.catalog.services.inventory`) — the same surface used by
`wt task` and `wt step`. `WorkflowDefinition` declares a
`schema_validator: ClassVar[SchemaValidator]` bound to `WORKFLOW_VALIDATOR`, which the
catalog's internal `_validate_definition` helper detects automatically and runs against
the parsed YAML *before* constructing the model. There is no separate workflow
discovery/inventory/resolve/validate pipeline; a non-ok `DefinitionResolutionResult`
carries schema or lookup errors in `result.errors`, formatted for CLI panels by
`format_workflow_run_resolve_failure` in
[src/worktree/core/workflows/services/renderer.py](../../src/worktree/core/workflows/services/renderer.py).

### `WorkflowDefinition`

Model: [src/worktree/core/workflows/models.py](../../src/worktree/core/workflows/models.py)
(`model_config = {"extra": "ignore", "populate_by_name": True}` — see
**Blueprint models and `extra: "ignore"`** below for why this diverges from the
project-wide `extra: "forbid"` default). Read the model for the exact field list;
non-obvious behavior the fields don't convey:

- `version` accepts JSON `1` or the string `"1.0"`; anything else fails a
  post-validator, not the JSON Schema (the schema's `oneOf` already narrows this,
  so the Pydantic check is defense-in-depth for programmatic construction).
- `id` defaults to `name` when omitted from the *parsed model*. The JSON Schema
  requires `id` in `required` (`v1/workflow.json`), so a workflow YAML that omits
  `id` and relies on this default is rejected at the schema gate before the model
  ever runs — the schema and the model disagree about whether `id` is optional.
  If the model's default-from-`name` behavior is meant to be reachable from YAML,
  drop `id` from workflow.json's `required` list; if it isn't, this default only
  serves programmatic `WorkflowDefinition(...)` construction and that should be
  said explicitly at the model, not left implicit.
- `steps` is `list[StepDefinition | LoopStepBlock] | None`; a top-level
  `_apply_blueprint_defaults` validator fills `on_failure` on standard steps only
  (see **`BlueprintDefaults` and `defaults.on_failure`** below) before the union
  discriminates each item.
- `inputs: dict[str, ParameterInput]` — see **Inputs and interpolation** below.

## Task blueprint resolution & execution

**[status: describes `core/task/`, unused by the live CLI — see
**Unified blueprint execution** above.]**

Task blueprints live under `.worktree/catalog/tasks/` and resolve through the
same catalog inventory path as workflows.

### `TaskDefinition`

Model: [src/worktree/core/task/models.py](../../src/worktree/core/task/models.py)
(`model_config = {"extra": "ignore", "populate_by_name": True}` — see
**Blueprint models and `extra: "ignore"`** below). Read the model for the exact
field list (`name`, `description`, `summary`, `use_sandbox`, `inputs`, `defaults`,
`steps`); non-obvious behavior:

- `inputs: dict[str, ParameterInput]` declares typed task parameters — see
  **Inputs and interpolation** below. `TaskDefinition` has no `schema_validator`
  at all (Pydantic-only validation, unlike `WorkflowDefinition`). If that
  asymmetry is intentional rather than a second instance of the schema-drift
  problem described in **Changing config or workflow shape** below, say so here
  explicitly.
- `defaults: BlueprintDefaults` only carries `on_failure` (extra keys forbidden
  on `BlueprintDefaults` itself, independent of `TaskDefinition`'s own
  `extra: "ignore"`).

Before validation, `_fill_step_shorthand_defaults` normalizes each raw step dict:

- Missing/empty `id` → slug from `name`, else `step-{idx}` (1-based).
- Bare `command: ...` with no `run` / `uses` / `type` → mapped to `run`.
- If the step omits `on_failure` and `defaults.on_failure` is set → copy that
  `FailureSpec` onto the step (fill-if-omitted only; explicit step values win
  unchanged with no field merge).

Example:

```yaml
name: lint-fix
description: Run project linters
use_sandbox: true
defaults:
  on_failure: continue
steps:
  - command: ruff check .
  - id: tests
    name: unit tests
    run: pytest -q
    on_failure: abort   # explicit wins
```

Exceptions subclass the shared definition bases in
[src/worktree/common/exceptions.py](../../src/worktree/common/exceptions.py):

- `TaskLoadError(DefinitionLoadError)`
- `TaskValidationError(DefinitionValidationError)`

### Resolve: `resolve_and_load_task`

[src/worktree/core/task/services/loader.py](../../src/worktree/core/task/services/loader.py)

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
[src/worktree/core/task/services/renderer.py](../../src/worktree/core/task/services/renderer.py).

### Execute: `run_task`

[src/worktree/core/task/services/runner.py](../../src/worktree/core/task/services/runner.py)

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
`observer`) and delegates to `run_steps`. Plain failure text formatting lives in
`core/task/services/renderer.py` (`format_task_run_failure`).

## Inputs and interpolation

`TaskDefinition.inputs` and `WorkflowDefinition.inputs` both declare
`dict[str, ParameterInput]` — typed parameters a blueprint author can require or
default, and that step authors can reference from `command` / `prompt` /
`script_path` / `run` / `env` values. Models live in
[src/worktree/core/inputs/models.py](../../src/worktree/core/inputs/models.py);
resolution and interpolation live in `core/inputs/services/`.

- `ParameterInput` (`extra: "forbid", strict: True`): `type` (`string` | `boolean` |
  `integer`, default `string`), `description`, `required` (default `False`),
  `default`, `aliases` (list of CLI flag strings, e.g. `["-m", "--message"]`; a bare
  string coerces to a one-element list).
- **CLI parsing** (`resolve.py`): `parse_cli_input_args` walks trailing CLI tokens
  against declared `aliases` plus the generic `-i`/`--input key=value` override.
  Bare boolean aliases (no `=`, next token looks like another flag) set `True`
  without consuming a value. Unknown `-i`/`--input` keys warn and are dropped;
  unrecognized tokens warn and are skipped (never a hard parse failure by
  themselves). `resolve_inputs` layers explicit overrides over parsed CLI values,
  then fills declared `default`s, then reports any still-missing `required` names
  in `InputResolveResult.missing`. `ok` is `not errors and not missing`.
- **Interpolation** (`interpolate.py`): step `command`, `prompt`, `script_path`,
  `run`, and string values inside `env` may contain `${{ inputs.<name> }}`
  placeholders. `interpolate_step_fields` substitutes resolved values (coerced to
  `str`) and returns a copy of the step; an unresolved placeholder (name not in the
  resolved `inputs` dict) is left as literal text rather than raising. This runs at
  execution time — `Step.execute()` and `runner._prepare_step_for_execution`, not at
  blueprint load — so a step's authored YAML always shows the placeholder, never a
  substituted value.
- `format_missing_inputs_error` / `format_input_error_message` (`resolve.py`) build
  the CLI-facing message for a missing-required-input failure, including a
  `wt <kind> run <name> <alias> <value>` / `-i <name>=<value>` usage hint per
  missing input — reuse these rather than hand-writing a new missing-input message.

## Shared step execution layer (`core/runtime/`)

Package: [src/worktree/core/runtime/](../../src/worktree/core/runtime/)
(`models.py`, `engine.py`, `failure.py`, `exceptions.py`). Used by `run_task` and
blueprint execution services.

### `RunContext`

Immutable frozen dataclass. Read `core/runtime/models.py` for the exact field list
(`steps`, `cwd`, `use_sandbox`, `keep`, `agent`, `observer`, `inputs`,
`non_interactive`, `failure_prompter`, `pause_store`, `resume_from`). Non-obvious:

- `inputs: dict[str, str | int | bool] | None` is the *resolved* input values
  (post `resolve_inputs`), threaded into `execute_step`'s `context["inputs"]` for
  interpolation — not the blueprint's `inputs: dict[str, ParameterInput]`
  declarations.
- `non_interactive`, `failure_prompter`, `pause_store`, and `resume_from` only
  matter for `prompt_user` steps; see **Pause, checkpoint, and resume** below.
  A library/CI caller that never uses `prompt_user` can ignore all four.

### `RunObserver`

Optional protocol hooks (no-ops when `observer is None`), defined in
`core/runtime/models.py`: `on_sandbox_ready`, `on_step_start`, `on_step_done`,
`on_sandbox_cleanup`. `core.runtime.observer` implements `LiveObserver` against
Rich output.

### `RunOutcome`

Pydantic model (`extra: "forbid", strict: True`) in `core/runtime/models.py`. Read
the model for the exact field list (`status`, `step_results`, `error_message`,
`warnings`, `sandbox_kept`, `sandbox_path`, `session_id`). Non-obvious:

- `ok` is true iff `status == RunStatus.COMPLETED`. A non-empty `warnings` never
  flips `ok` — warnings are informational (e.g. "failed to persist pause
  checkpoint"), not failures.
- `status` can also be `PAUSED` (see below) or `CANCELLED` (`KeyboardInterrupt`
  during the step loop, outside a pending prompt).
- `session_id` is not stamped by `run_steps` itself; it is `None` unless the
  caller (a session/history-aware layer above `run_steps`) sets it.

### `run_steps(context) -> RunOutcome`

Flow in [src/worktree/core/runtime/engine.py](../../src/worktree/core/runtime/engine.py):

1. **Sandbox setup** (`_setup_sandbox`): if `context.resume_from` is set, rebuild
   the sandbox session from the checkpoint instead of creating a new one (see
   **Pause, checkpoint, and resume**). Otherwise, if `use_sandbox` is false,
   execute in `cwd` and notify `on_sandbox_ready(..., active=False)`; else
   `GitSandboxManager.create_sandbox_result()`. Setup failure returns
   `status=failed` with `error_message` and no steps run.
2. **Step loop** (`_run_step_loop`): starts at `resume_from.next_step_index` when
   resuming, else `0`. For each step, notify start, call `execute_step(step,
   sandbox_path=target_dir, context=step_context)`, notify done. A failed
   `StepResult` triggers `_handle_failed_step`, which computes the effective
   terminal policy (see **Runtime failure orchestration** below) and either
   continues, aborts (`status=failed`), or invokes the failure prompter
   (`status=paused` on `PromptUserInterruptedError`, i.e. Ctrl-C while a
   checkpoint was already persisted). Plain `KeyboardInterrupt` elsewhere →
   `status=cancelled`.
3. **Cleanup** (`finally`): when the loop paused, the sandbox is *kept*
   (`sandbox_kept=True`) regardless of `context.keep`, so a later resume can reuse
   it. Otherwise, unless `keep` is true, best-effort `cleanup_sandbox`; notify
   `on_sandbox_cleanup`.

Domain packages must not re-implement this loop or sandbox lifecycle.

## Pause, checkpoint, and resume

A `prompt_user` terminal failure (see **Runtime failure orchestration** below) can
suspend a run mid-blueprint rather than forcing an immediate abort/continue/retry
decision, so a workflow can be resumed later (e.g. from a different process, after
a human looks at the failure). Models: `RunCheckpoint`, `FailurePromptDecision`,
`FailurePrompter`, `RunPauseStore` in `core/runtime/models.py`.

- `RunCheckpoint` (`extra: "forbid", strict: True`) is the JSON-serializable pause
  payload: enough sandbox identity (`sandbox_path`, `sandbox_id`, `sandbox_name`,
  `sandbox_branch`, `sandbox_base_commit`, `use_sandbox`), run options (`keep`,
  `agent`, `inputs`), the pending step (`pending_step_id`, `pending_result`,
  `diagnostic`), and `next_step_index` to resume the loop without re-running
  completed steps or losing their `step_results`. `parse_checkpoint(raw) ->
  RunCheckpoint | None` parses JSON text, returning `None` (not raising) on
  missing or corrupt input.
- `FailurePrompter` is the injectable interactive decision point
  (`prompt_step_failure(*, step, result, diagnostic) -> FailurePromptDecision`,
  one of `RETRY` / `CONTINUE` / `ABORT`). It "must not block for non-interactive
  callers" — see **Runtime failure orchestration** for the non-interactive
  degradation rule.
- `RunPauseStore` is the domain adapter that persists/clears the checkpoint
  (`save_checkpoint`, `clear_pause`); `run_steps` calls it (via
  `context.pause_store`) right before invoking the prompter, and clears it once
  the prompter returns. `context.pause_store is None` (the default) means no
  checkpoint is ever persisted, so a `prompt_user` failure there can only
  abort/continue/retry in-process, never pause.
- **Live path**: `Engine` (see **Unified blueprint execution** above) wires its
  own private `_DbPauseStore` (`core/engine/engine.py`, same shape as
  `RunPauseStore`, not exported) for both `.run` and `.resume`, and
  `ResumableRun` is the live classifier/loader analogous to the paragraph below.
  `wt resume` calls `Engine.resume`, never `resume_workflow`.
- **Legacy path** (`core/workflows/`, unused by the live CLI):
  `WorkflowPauseStore` ([src/worktree/core/workflows/services/pause.py](../../src/worktree/core/workflows/services/pause.py))
  implements `RunPauseStore` against `RunsRepository`, storing
  `checkpoint.model_dump_json()` and marking the run row `PAUSED`.
  `resume_workflow(session_id, cwd, *, failure_prompter=None, non_interactive=False,
  observer=None) -> WorkflowResumeResult`
  ([src/worktree/core/workflows/services/resume.py](../../src/worktree/core/workflows/services/resume.py))
  loads that row, validates it's `PAUSED` with a parseable checkpoint and an
  existing sandbox path (when `use_sandbox` was true), re-resolves the workflow
  definition and confirms the checkpoint's `pending_step_id` still exists in it,
  then re-enters `run_steps` with `resume_from=checkpoint`. `WorkflowResumeResult`
  (`extra: "forbid", strict: True`) statuses: `ok`, `not_found`, `wrong_status`,
  `missing_sandbox`, `corrupt_checkpoint`, `failed` — `ok` requires
  `status == OK and not errors`. This is exercised only by `core/workflows/`'s
  own tests today.
- Task execution (`run_task`, also legacy) does not wire a `pause_store` either.
  `Engine` (live path) wires the same `_DbPauseStore` for both task- and
  workflow-kind blueprints, so this asymmetry is specific to the legacy
  `task`/`workflows` split and does not carry over to the live path.

## Catalog templates & seeding

Packaged scaffolds live under
[src/worktree/core/catalog/templates/](../../src/worktree/core/catalog/templates/)
(`workflows/`, `tasks/`, `steps/`), including `default.yml` per type and curated
`wt/` seed trees. Path helper: `get_catalog_templates_dir()` in
[src/worktree/common/fs.py](../../src/worktree/common/fs.py).

Curated step seeds ship under `templates/steps/wt/`
(`git-sync-base`, `ai-planner`, `ai-code-patcher`, `run-tests`, `ai-reviewer`)
and seed into `.worktree/catalog/steps/wt/`. Workflow seeds under
`templates/workflows/wt/` may reference them with `uses: wt/<name>` (for example
`wt/ai-code-patcher`).

Seeding ([src/worktree/core/catalog/services/seeder.py](../../src/worktree/core/catalog/services/seeder.py)):

- `seed_catalog_templates(item_type, cwd=None, *, force=False) -> SeedResult` —
  copies packaged `wt/` files into
  `.worktree/catalog/<type>s/wt/` (skips existing files unless `force`;
  a target path that already exists as a directory is recorded as an error, not
  silently skipped).
- `seed_all_catalog_templates(cwd=None, *, force=False) -> SeedResult` —
  seeds `workflow`, `task`, and `step` and aggregates `SeedResult`
  (`created_files`, `skipped_existing_files`, `overwritten_files`, `warnings`,
  `errors` — see the model in `core/catalog/models.py`).

CLI template surfaces (no separate `wt template` command group):

- `wt catalog list --type template` — lists packaged `default.yml` scaffolds
  (type + relative path table).
- `wt catalog show <name>` — after a local catalog miss, falls back to packaged
  templates matching the name and prints raw YAML via
  `render_template_show_content`.

## Workflow formatters

Pure formatters (no IO/print/exit) for resolve/validate failure panel bodies live in
[src/worktree/core/workflows/services/renderer.py](../../src/worktree/core/workflows/services/renderer.py):

- `format_workflow_run_resolve_failure(result: DefinitionResolutionResult[CatalogRecord]) -> str`
- `format_workflow_run_validate_failure(result: DefinitionValidationOutcome) -> str`

Resolve body: `"\n\n".join(errors)` or `Failed to resolve workflow.`
Validate body: `"\n\n".join(errors)` or `Workflow definition is invalid.`

## Changing config or workflow shape

1. Update the relevant JSON Schema (`v1/config.json` or `v1/workflow.json`).
2. Update `CANONICAL_V1_DEFAULTS` (config) or the packaged templates under
   `core/catalog/templates/` (workflows/tasks/steps `default.yml` and curated
   `wt/` seeds). See **Catalog templates & seeding** above for list/show fallback.
3. Update the corresponding Pydantic model. For step/blueprint shape, that's
   `core/blueprint/models.py`'s `BlueprintDefinition` (the live model) — and, if
   you're intentionally keeping the legacy packages in step with it rather than
   letting them diverge further, also `core/workflows/models.py` /
   `core/task/models.py`. For config: `core/config/models.py`. For inputs:
   `core/inputs/models.py`.
4. Add/adjust tests under the matching `tests/core/...` package.

Bump the schema version (`config_v2.json`, etc.) instead of making breaking
changes to a `v1` schema that users may already have on disk.

**`v1/workflow.json`'s inline step shape must mirror `StepDefinition`'s
inline-authoring shape exactly.** `WorkflowDefinition.schema_validator` runs
the JSON Schema gate *before* Pydantic model validation (see **Workflow
blueprint resolution** above), so if `standard_step` in `workflow.json` is
missing a field `StepDefinition` accepts for inline steps, any workflow YAML
that inlines that shape (rather than using `uses:`/`run:`) gets rejected at the
schema gate with a confusing "not valid under any of the given schemas" error,
even though the model would accept it.

**This is currently the case, not just a historical risk**: as of this writing,
`standard_step` in `workflow.json` has no `type`, `command`, `description`, or
`script_path` properties, while `StepDefinition` accepts all four for inline
`type=command` / `type=agent` / `type=script` steps (see **StepDefinition
Model** below). Every packaged step template under
`core/catalog/templates/steps/wt/*.yml` uses that inline `type:`/`command:`
shape, so `workflow.json` is out of sync with the templates it's meant to
validate. When you add or fix a field on `StepDefinition`'s inline shape,
update `standard_step` in the same change, and add (or keep passing) a test
that round-trips every file under `core/catalog/templates/steps/**/*.yml`
through both `WORKFLOW_VALIDATOR` and `StepDefinition` so this class of drift
fails a test instead of shipping silently.

**A second, related asymmetry**: `workflow.json`'s top-level `required` list
includes `id`, but `WorkflowDefinition.id` defaults to `name` when omitted (see
**`WorkflowDefinition`** above). A workflow YAML that omits `id` to use that
default is schema-invalid before the model ever runs. Resolve this the same
way: either drop `id` from `required`, or make the model require it too — don't
leave the schema stricter than the model it's supposed to gate.

## Step Definition Schema and Execution Engine

Step primitives stored in `.worktree/catalog/steps/` represent reusable blueprints shared by
catalog steps, workflow steps, and task steps. Models and engine live in
[src/worktree/core/step/](../../src/worktree/core/step/).

### `FailurePolicy` and `FailureSpec`

`FailurePolicy` (`src/worktree/core/step/models.py`) is a `StrEnum`: `abort`, `continue`,
`prompt_user`, `retry`. `FailurePolicy.context("terminal")` returns `{abort, continue,
prompt_user}` (excludes `retry`); any other name returns the full set.

`FailureSpec` is the normalized `on_failure` directive (`extra: "forbid"`, not
`strict`). Read the model for the exact field list (`action`, `max_retries`,
`backoff_ms`, `on_max_retries`); the one non-obvious rule is that
`on_max_retries` is validated against `FailurePolicy.context("terminal")`, so
`on_max_retries: retry` (retry-on-retry-exhaustion) is rejected.

### `BlueprintDefaults` and `defaults.on_failure`

`BlueprintDefaults` (`extra: "forbid"`, not `strict`) is the optional root-level
`defaults` block on `TaskDefinition` and `WorkflowDefinition`: a single
`on_failure: FailureSpec | None` field with the same string-or-object coercion as
`StepDefinition.on_failure`.

Resolution order when building concrete steps at load/normalize time (not inside
`execute_step`):

1. Step already has `on_failure` → keep unchanged (no deep merge)
2. Else blueprint `defaults.on_failure` is set → **copy** that `FailureSpec` onto the step
3. Else → step keeps the existing model default (`FailureSpec(action=abort)`)

This is inheritance packaging only — not a second post-step escalation ladder.
Top-level standard steps are filled for tasks and workflows; nested loop `do[]`
fill is deferred to the loop engine.

### `StepDefinition` Model

`StepDefinition` (`extra: "forbid", strict: True, populate_by_name: True`) is the
single model for catalog step blueprints, workflow steps, and task steps. Read the
model for the exact field list (`id`, `uses`, `run`, `name`, `type`, `description`,
`command`, `prompt`, `script_path`, `tools`, `env`, `timeout_seconds`, `assert_`
aliased to `assert`, `on_failure`). The step-shape validator is the part not
visible from the field list alone — it enforces exactly one of `run` / `uses` /
inline `type`:

- `run` cannot be combined with `uses`, `command`, `type`, `prompt`,
  `script_path`, or `tools`.
- Inline `type=command` requires `command`; `type=agent` requires `prompt`;
  `type=script` requires `script_path`.
- If none of `run`, `uses`, or `type` is set, validation fails.

`StepDefinition` does not support a `with`/override mechanism in v1 — `uses`
steps load the referenced step definition as-is. `command` / `prompt` /
`script_path` / `run`, and string values in `env`, may contain
`${{ inputs.<name> }}` placeholders — see **Inputs and interpolation** above.

### `LoopStepBlock`

`LoopStepBlock` also lives in `core/step/models.py` (`extra: "ignore"`, not
`strict` — see **Blueprint models and `extra: "ignore"`** below). Read the model
for the exact field list (`id`, `type: Literal["loop"]`, `max_iterations`,
`until`, `do`, `on_max_iterations`). Non-obvious: `on_max_iterations` is
restricted to `FailurePolicy.context("terminal")` just like `FailureSpec.
on_max_retries` — a value of `retry` raises a validation error.

### Step Loader & Resolver

Functions in `core/step/services/` (re-exported from `worktree.core.step`):

- `load_step_definition(path: Path) -> StepDefinition`: Loads and parses a step YAML file. Raises `StepNotFoundError` if file missing/unreadable, `StepValidationError` on YAML or Pydantic validation error.
- `load_step_by_id(step_id_or_name: str, cwd: Path | None = None) -> StepDefinition`: Resolves from `.worktree/catalog/steps/` only (local catalog after seed; no package-resource bypass at runtime). Direct path first: `wt/<name>` → `.worktree/catalog/steps/wt/<name>.yml` (also `.yaml`); unprefixed `<name>` → `.worktree/catalog/steps/<name>.yml`. If no direct file, scan YAML under the steps tree including `wt/` for matching `id`/`name` (invalid siblings skipped during scan). Missing directory or no match → `StepNotFoundError`.
- `resolve_step_definition(step: StepDefinition, *, cwd: Path | None = None) -> StepDefinition`: Normalizes a step with `uses` (loads the referenced step via `load_step_by_id()`, including `uses: wt/<name>`) or `run` (synthesizes `type=command`, `command=run`) into a concrete, directly executable `StepDefinition`. Inline `type` steps pass through unchanged.

`Step` ([src/worktree/core/step/step.py](../../src/worktree/core/step/step.py)) is a
higher-level handle over the same functions, used where callers want input
interpolation applied before execution: `Step.load(source, catalog=None)` accepts
a `StepDefinition`, a raw dict (validated against `StepDefinition`), or a catalog
name/SHA (via `Catalog().resolve_step`); `.execute(sandbox_path, *, inputs=None,
context=None)` calls `interpolate_step_fields` when `inputs` is given, then
delegates to `execute_step`. It does not replace `execute_step` or the loader
functions above — it composes them for the input-interpolation call path.

### Step Execution Engine

`execute_step(step: StepDefinition, sandbox_path: Path, context: dict | None = None) -> StepResult`:

- Resolves `uses`/`run` steps via `resolve_step_definition()` before dispatch, then
  interpolates `${{ inputs.* }}` placeholders when `context["inputs"]` is set.
- Executes the step primitive inside `sandbox_path` with isolated working directory `cwd=sandbox_path`.
- Enforces process timeouts via `timeout_seconds`.
- After a successful primitive dispatch (`status="completed"`), evaluates `step.assert_` via
  `evaluate_assertions` when an `assert` block is present. Assertion failure rewrites the
  attempt to `status="failed"` with a multi-line diagnostic in `error_message` before
  `on_failure` retry/continue logic runs.
- Handles step-local `on_failure` recovery only:
  - `action == "retry"`: retries execution up to `max_retries` attempts, sleeping `backoff_ms` milliseconds between attempts. After the final failed attempt, evaluates `on_max_retries`: `continue` returns `status="ignored"` (`ok=True`); `abort`/`prompt_user` return `status="failed"`.
  - `action == "continue"` (no retry): a single failed attempt returns `status="ignored"` (`ok=True`).
  - `action == "abort"` / `"prompt_user"` (no retry): a single failed attempt returns `status="failed"`. `execute_step` never opens an interactive prompt; `prompt_user` only classifies the attempt as terminal failure for runtime orchestration.
- Returns `StepResult` (`core/step/runner.py`, `extra: "forbid", strict: True`):
  `step_id`, `status` (`completed`, `failed`, `ignored`), `exit_code`, `stdout`,
  `stderr`, `duration_seconds`, `attempts`, `error_message`. `ok` property returns
  `True` for `completed` or `ignored`.

### Runtime failure orchestration (`run_steps`)

Multi-step stop/continue/prompt decisions live in `core/runtime/` (`run_steps`,
`FailurePrompter`), not in `execute_step` and not in a second task/workflow
policy engine.

When a step returns `status="failed"`, runtime computes the **effective terminal
policy** from the resolved `StepDefinition.on_failure`:

- if `action == retry` → effective = `on_max_retries`
- else → effective = `action`

Effective value is always terminal (`abort` / `continue` / `prompt_user`; never
`retry`). Behavior:

- `abort` → stop the step loop; `RunOutcome.status == FAILED`
- `continue` on a `failed` result is defensive only (step-local continue already
  maps to `ignored`); runtime treats it as non-fatal and proceeds
- `prompt_user` → invoke `RunContext.failure_prompter` when interactive; honor
  retry (re-enter `execute_step` for the same step), continue (`ignored` +
  `user continued after prompt_user` marker), or abort (`FAILED`). If a
  `pause_store` is configured, a `RunCheckpoint` is persisted immediately before
  the prompter is invoked (see **Pause, checkpoint, and resume** above), and a
  `KeyboardInterrupt` while awaiting the prompter's decision becomes
  `status=paused` rather than `status=cancelled`.

Non-interactive degradation (`RunContext.non_interactive`, CLI
`--non-interactive`, or no TTY / missing prompter): `prompt_user` emits a
warning and behaves as `abort` without blocking on stdin. Default when
`failure_prompter is None` is abort (safe for library/CI callers).

There is no run-level retry policy in YAML. The only automatic re-execution of a
step primitive is inside `execute_step`; user-chosen retry at the prompt is a
runtime re-entry of `execute_step` (full step-local budget applies again).

#### Assert Block

Optional YAML key `assert` maps to `StepDefinition.assert_` (`StepAssert` in
[src/worktree/core/step/models.py](../../src/worktree/core/step/models.py)). The same model is used for
catalog steps, task steps, and workflow steps.

Public evaluation entrypoint:
[src/worktree/core/step/assertions/](../../src/worktree/core/step/assertions/)
(`evaluate_assertions` re-exported from `worktree.core.step`).

When the `assert` block is present, `exit_code` is **always** evaluated. If `exit_code` is omitted,
expected exit code defaults to `0`. Every other key runs only when set. Process/output checks use
combined `stdout\nstderr` except `json_match`, which parses **stdout only**.

This is the YAML authoring surface for `assert:` (accepted keys, types, and behavior) — kept as a
table because it's a stable user/agent-facing contract, not a code-mirror convenience:

| Key | Accepted type | Behavior |
|-----|---------------|----------|
| `exit_code` | `int` \| `list[int]` \| omit | Actual process exit must be in the expected set; omit → expect `0` |
| `output_contains` | `str` \| `list[str]` | Each substring must appear in combined output |
| `output_not_contains` | `str` \| `list[str]` | None of the substrings may appear in combined output |
| `regex_match` | `str` | Regex must match somewhere in combined output |
| `json_match` | object with `path`, `operator`, `value` | Parse stdout as JSON; compare dot-path value (`eq`, `neq`, `contains`, numeric ops) |
| `file_exists` | `str` \| `list[str]` | Relative path(s) under the sandbox must exist as files |
| `file_not_exists` | `str` \| `list[str]` | Relative path(s) must not exist |
| `file_not_empty` | `str` \| `list[str]` | Relative path(s) must exist as non-empty files |

File assert paths must be non-empty relative paths without `..` segments (validated on the model).

`evaluate_assertions(...) -> AssertionResult` (`core/step/models.py`, `extra: "forbid",
strict: True`): `passed`, `failed_conditions`, `message`. `passed` is true only when
`failed_conditions` is empty. On failure, `message` is the newline-joined condition
strings; the runner prefixes them with a step label and `[FAIL]` markers in
`StepResult.error_message`.

Example catalog step (`.worktree/catalog/steps/*.yml` shape) with a full `assert` block:

```yaml
id: step_pytest_verify
name: run-pytest
type: command
description: Run the test suite and verify results
command: pytest --json-report --json-report-file=report.json
assert:
  exit_code: [0, 1]
  output_contains: "0 errors"
  output_not_contains: ["FATAL", "PANIC"]
  regex_match: "([0-9]+) passed"
  json_match:
    path: "summary.status"
    operator: "eq"
    value: "APPROVED"
  file_exists: "report.json"
  file_not_exists: "tmp/lock"
  file_not_empty: "coverage.json"
```

## Blueprint models and `extra: "ignore"`

`TaskDefinition`, `WorkflowDefinition`, `BlueprintDefaults`, and `LoopStepBlock` all
use `extra: "ignore"` (and no `strict: True`) instead of the project-wide
`extra: "forbid", strict: True` default (see
[code-conventions.md](code-conventions.md#pydantic-models)). `StepDefinition`,
`StepAssert`, `FailureSpec`'s sibling models, and everything in `core/runtime/` and
`core/config/` do use the strict default — so this is a real, scoped deviation, not
a project-wide relaxation.

The likely rationale: these four are the *hand-authored YAML entry points* into the
blueprint system, and `extra: "ignore"` lets a blueprint author leave in a comment
field, a future key, or a typo'd sibling key from copy-pasting another blueprint
without hard-failing the whole file — whereas `StepDefinition` (the thing actually
executed) and every internal result/outcome model should fail loudly on an unknown
key. If that's the real reason, it should be a one-line comment at each
`model_config`, not left to be inferred from this doc. If it isn't the reason, these
four should move to `extra: "forbid"` like everything else.
