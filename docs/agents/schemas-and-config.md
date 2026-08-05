# Schemas and Config

## Versioned JSON Schemas

`getworktree/schemas/config_v1.json` and `workflow_v1.json` are the source of truth
for what a valid `.worktree/config.json` and workflow YAML file look like. Both are
validated through `SchemaValidator` ([getworktree/common/schema_validation.py](../../getworktree/common/schema_validation.py)),
a thin wrapper over `jsonschema.Draft202012Validator` that returns a
`ValidationResult(ok, errors)` instead of raising.

### Config V1 contract

`config_v1.json` is the **only** structural source of truth for config V1
(draft 2020-12). Runtime validation uses packaged `CONFIG_VALIDATOR`; do not
duplicate the schema in Python.

Strictness:

- Root and every nested object use `additionalProperties: false` (unknown keys
  fail validation).
- Top-level `required`: `version`, `project`, `paths`, `sandbox`, `workflow`,
  `agent`, `patch`, `approval`, `history`, `doctor`, `prune`, `telemetry`.
- `version` is integer `const: 1`.

Enums (exact tokens):

- Config `agent.provider`: `local` | `ollama` | `cursor` | `gemini` |
  `copilot` | `openai` | `anthropic` | `azure_openai` | `custom` (runtime
  factory supports **`local`**, **`ollama`**, **`cursor`**, **`gemini`**, and
  **`copilot`**; other tokens remain schema-valid for future providers)
- Workflow `agent.provider` (`workflow_v1.json`): `local` | `ollama` | `cursor` |
  `gemini` | `copilot`
- `patch.strategy`: `unified_diff`

For `wt workflow run`, **workflow** `agent.provider` selects the adapter; **config**
`agent.model` / `endpoint` / `temperature` / `max_tokens` fill the request.
Ollama uses `config.agent.model` + `config.agent.endpoint` (or `OLLAMA_HOST`).
Cursor uses `config.agent.model` and `CURSOR_API_KEY`. Gemini uses
`GEMINI_API_KEY`. Copilot uses `GH_TOKEN` or `GITHUB_TOKEN`. Cursor, Gemini,
and Copilot mutate the sandbox directly through the shared base in
`core/workflows/agents/cli_mutation.py`; local and Ollama still return diffs.

Notable bounds / string rules:

- Path strings (`paths.*`, `sandbox.base_ref`): non-empty (`minLength: 1`)
- Positive integers (`minimum: 1`): sandbox/workflow attempt and timeout fields,
  `agent.max_tokens`, `patch.max_files` / `max_patch_kb`, `history.max_sessions`
- `agent.temperature`: number in `[0, 2]`
- `prune.artifact_ttl_days`: integer `minimum: 0`
- `agent.model` / `agent.endpoint`: `string | null`; non-null strings must be
  non-empty
- `project.name` / `project.initialized_at`: `string | null` (loader maps null
  name to `"unnamed_project"` after schema validation)

Not expressed in the JSON Schema (validator-engine / runtime territory):

- Cross-field limits (e.g. `workflow.default_max_attempts <= max_attempts_hard_limit`)
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
`WorktreeConfig` (full V1 surface: version, project, paths, sandbox, workflow, agent,
patch, approval, history, doctor, prune, telemetry), and `errors` is empty.
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
| `CONFIG_SEMANTIC_MAX_ATTEMPTS` | error | `workflow.default_max_attempts` > hard limit |
| `CONFIG_SEMANTIC_PATH_INVALID` | error | any `paths.*` value has NUL/newline |
| `CONFIG_WARN_AGENT_MODEL_MISSING` | warning | non-`local` provider without model |
| `CONFIG_WARN_AGENT_ENDPOINT` | warning | non-null endpoint not absolute http(s) URL |
| `CONFIG_WARN_SANDBOX_LIMIT` | warning | `sandbox.max_active_sandboxes` > 10 |

Warnings never alone make `ok=false`. Ordering: IO/parse single error first;
else structural block; then semantic errors (max-attempts, then path keys in
field order). Warnings follow FR-7 rule order (model, endpoint, sandbox limit).

Commands must call this API rather than re-implementing schema or semantic
workflows.

## `wt config validate` CLI

Command entry: `getworktree.commands.config.command.config_validate_command`.
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
  `version`, `project`, `paths`, `sandbox`, `workflow`, `agent`, `patch`,
  `approval`, `history`, `doctor`, `prune`, `telemetry`. Nested keys follow the
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

Command entry: `getworktree.commands.config.command.config_show_command`.

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

Command entry: `getworktree.commands.config.command.config_set_command`.
Registration: `wt config set <key> <value>` under `config_app` in
[getworktree/cli.py](../../getworktree/cli.py).

| Condition | Exit | Output |
|-----------|------|--------|
| success | `0` | green success: `Config updated: <key> = <value>` |
| any non-ok result | `1` | red panel **Config Error** with `"\n\n".join(result.errors)` |

## Workflow file discovery API

Filesystem discovery for workflow definition candidates lives in
[getworktree/core/workflows/discovery.py](../../getworktree/core/workflows/discovery.py).
This layer only resolves the workflows directory and enumerates candidate YAML
paths. It does **not** parse YAML, validate `workflow_v1.json`, print, call
`sys.exit`, or create/mutate workflow files.

Default relative directory: `.worktree/workflows` (`DEFAULT_WORKFLOWS_DIR`).
Config key: `paths.workflows_dir`. Explicit `workflows_dir` wins over config.

### Primary API

`discover_workflow_files(cwd=None, *, workflows_dir=None, use_config=True) -> WorkflowDiscoveryResult`
is the primary surface for later `wt workflow list|show|run`.

`resolve_workflows_dir(cwd=None, *, workflows_dir=None, use_config=True) -> tuple[Path, list[str]]`
returns `(absolute_workflows_dir, resolution_errors)` using the same resolution
rules.

```python
class WorkflowDiscoveryStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    NOT_A_DIRECTORY = "not_a_directory"
    UNREADABLE = "unreadable"
    CONFIG_UNAVAILABLE = "config_unavailable"


class WorkflowDiscoveryResult(BaseModel):
    status: WorkflowDiscoveryStatus
    workflows_dir: Path  # absolute path resolved / attempted
    paths: list[Path]  # absolute candidate file paths
    errors: list[str]

    @property
    def ok(self) -> bool: ...  # status == OK
```

Resolution order:

1. Explicit `workflows_dir` (absolute as-is after resolve; relative against `cwd`)
2. Else if `use_config`: `load_config_result` → `config.paths.workflows_dir`
3. Else: `cwd / ".worktree/workflows"`

When config is required and load is not ok, status is `config_unavailable`
(no second config parser). Empty directories are success with `paths=[]`.

### Candidate inclusion (non-recursive)

Only direct children of `workflows_dir`. Include when all are true:

- regular file (`Path.is_file()`; skip dirs/sockets; broken symlinks skipped)
- name ends with `.yml` or `.yaml` (case-sensitive)
- name does not start with `.` or `_`

`paths` sorted by `Path.name` ascending (Unicode code-point), then absolute
path string as tiebreaker. Contents are never opened.

### Error codes

| Code | Status |
|------|--------|
| `WORKFLOW_DIR_NOT_FOUND` | `not_found` |
| `WORKFLOW_DIR_NOT_A_DIRECTORY` | `not_a_directory` |
| `WORKFLOW_DIR_UNREADABLE` | `unreadable` |
| `WORKFLOW_CONFIG_UNAVAILABLE` | `config_unavailable` |

Callers should use this API instead of ad-hoc `glob`/`iterdir` scans. Seeder
write paths remain separate.

## Workflow metadata parse API

Minimal list metadata for one workflow YAML file lives in
[getworktree/core/workflows/metadata.py](../../getworktree/core/workflows/metadata.py).
This layer reads a single path with `yaml.safe_load` and extracts identity
fields only. It does **not** run full `workflow_v1.json` validation, discover
siblings, print, call `sys.exit`, or mutate files.

### Primary API

`parse_workflow_metadata(path: Path) -> WorkflowMetadataParseResult`

```python
class WorkflowMetadataStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    NOT_A_FILE = "not_a_file"
    UNREADABLE = "unreadable"
    MALFORMED_YAML = "malformed_yaml"
    ROOT_NOT_MAPPING = "root_not_mapping"
    INVALID_METADATA = "invalid_metadata"


class WorkflowListMetadata(BaseModel):
    version: int
    name: str
    description: str
    source_path: Path  # absolute


class WorkflowMetadataParseResult(BaseModel):
    status: WorkflowMetadataStatus
    source_path: Path  # absolute
    metadata: WorkflowListMetadata | None
    errors: list[str]

    @property
    def ok(self) -> bool: ...  # status == OK
```

Minimal field contract (all checked; collect every problem):

| Field | Rules |
|-------|--------|
| `version` | present; JSON/YAML integer `1` only (`bool` invalid) |
| `name` | present; non-empty string matching `^[a-z0-9][a-z0-9-]*$` |
| `description` | present; non-empty string (`len >= 1`, no strip) |

Unknown extra root keys are allowed here. Incomplete full workflow bodies that
still satisfy the three identity fields are `ok` at this layer.

### Error codes

| Code | Status |
|------|--------|
| `WORKFLOW_META_NOT_FOUND` | `not_found` |
| `WORKFLOW_META_NOT_A_FILE` | `not_a_file` |
| `WORKFLOW_META_UNREADABLE` | `unreadable` |
| `WORKFLOW_META_MALFORMED_YAML` | `malformed_yaml` |
| `WORKFLOW_META_ROOT_NOT_MAPPING` | `root_not_mapping` |
| `WORKFLOW_META_MISSING_VERSION` | `invalid_metadata` |
| `WORKFLOW_META_INVALID_VERSION` | `invalid_metadata` |
| `WORKFLOW_META_MISSING_NAME` | `invalid_metadata` |
| `WORKFLOW_META_INVALID_NAME` | `invalid_metadata` |
| `WORKFLOW_META_MISSING_DESCRIPTION` | `invalid_metadata` |
| `WORKFLOW_META_INVALID_DESCRIPTION` | `invalid_metadata` |

Codes appear in `errors` strings so callers and tests can key off them.

## Workflow inventory API

Composition of discovery + per-file metadata parse lives in
[getworktree/core/workflows/inventory.py](../../getworktree/core/workflows/inventory.py).
This layer builds a partial-success inventory for future `wt workflow list`. It does
**not** run full `workflow_v1` validation, print, call `sys.exit`, or mutate files.

### Primary API

`build_workflow_inventory(cwd=None, *, workflows_dir=None, use_config=True) -> WorkflowInventoryResult`

```python
class WorkflowInventoryStatus(StrEnum):
    OK = "ok"
    DISCOVERY_FAILED = "discovery_failed"


class WorkflowInventoryValidEntry(BaseModel):
    name: str
    description: str
    version: int
    source_path: Path  # absolute


class WorkflowInventoryInvalidEntry(BaseModel):
    source_path: Path  # absolute
    status: str  # WorkflowMetadataStatus value
    errors: list[str]
    name: None = None
    description: None = None


class WorkflowInventoryResult(BaseModel):
    status: WorkflowInventoryStatus
    workflows_dir: Path  # absolute
    valid: list[WorkflowInventoryValidEntry]
    invalid: list[WorkflowInventoryInvalidEntry]
    warnings: list[str]
    errors: list[str]

    @property
    def ok(self) -> bool: ...  # status == OK
```

Semantics:

- Discovery not ok → `status=discovery_failed`, empty partitions, top-level
  `errors` copied from discovery; no per-file parses.
- Discovery ok (including empty dir, or some/all invalid files) → `status=ok`,
  top-level `errors` empty; per-file problems live only on `invalid` entries.
- `ok` means discovery succeeded and inventory was built. It does **not** mean
  `invalid` is empty. “All healthy” is `ok and not invalid`.
- On success: `len(valid) + len(invalid) == len(discovery.paths)`.
- `valid` sorted by `name`, then `source_path.as_posix()`.
- `invalid` sorted by `source_path.name`, then full path POSIX string.
- Duplicate logical names among **valid** entries remain listed; one warning per
  duplicated name:
  `Duplicate workflow name 'fix-tests' in multiple files: a.yml, b.yml`
  (file names sorted, comma-space separated). Invalid entries do not join
  duplicate-name warnings.

## Workflow resolve API

Name → path resolution on top of inventory lives in
[getworktree/core/workflows/resolve.py](../../getworktree/core/workflows/resolve.py).
This layer maps a logical workflow `name` to exactly one
`WorkflowInventoryValidEntry`. It does **not** parse full `workflow_v1` bodies, print,
call `sys.exit`, or mutate files.

### Primary API

`resolve_workflow_by_name(name, cwd=None, *, workflows_dir=None, use_config=True) -> WorkflowResolveResult`

Resolution always goes through `build_workflow_inventory` (same `cwd` / `workflows_dir`
/ `use_config`). Match is exact, case-sensitive equality on valid entry `name`
only. Invalid inventory entries never win.

```python
class WorkflowResolveStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    INVALID_NAME = "invalid_name"
    DISCOVERY_FAILED = "discovery_failed"


class WorkflowResolveResult(BaseModel):
    status: WorkflowResolveStatus
    name: str  # requested name echo
    workflows_dir: Path  # absolute
    entry: WorkflowInventoryValidEntry | None
    matches: list[WorkflowInventoryValidEntry]
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool: ...  # status == OK
```

### Status semantics

| Condition | `status` |
|-----------|----------|
| requested name fails `^[a-z0-9][a-z0-9-]*$` (before inventory IO) | `invalid_name` |
| inventory `discovery_failed` | `discovery_failed` (errors copied) |
| inventory ok, zero valid matches | `not_found` |
| inventory ok, one or more valid matches | `ok` (deterministic winner) |

Duplicate valid names do **not** fail: winner sort key is
`(source_path.name, source_path.as_posix())`; `matches` lists all matches in
that order; `entry` is `matches[0]`.

### Error / warning codes

| Code | Where | Status |
|------|--------|--------|
| `WORKFLOW_RESOLVE_INVALID_NAME` | `errors` | `invalid_name` |
| `WORKFLOW_RESOLVE_NOT_FOUND` | `errors` | `not_found` |
| `WORKFLOW_RESOLVE_DUPLICATE_NAME` | `warnings` | `ok` (duplicate case) |

Discovery failures keep inventory/discovery codes already present in those
`errors`. Inventory warnings are passed through; the resolver-specific
duplicate warning is appended after them when the requested name collides.

## Workflow validation API

Full `workflow_v1` validation for one definition lives in
[getworktree/core/workflows/validate.py](../../getworktree/core/workflows/validate.py).
Typed models live in
[getworktree/core/workflows/models.py](../../getworktree/core/workflows/models.py).
This engine is the authority for “is this workflow runnable / showable as valid.”
It does **not** print, call `sys.exit`, discover siblings, resolve names, or
create/mutate workflow files.

Shared schema binding:

```python
WORKFLOW_VALIDATOR = SchemaValidator(
    resources.files("getworktree.schemas") / "workflow_v1.json"
)
```

Exported from `getworktree.core.workflows`. Seeder imports the same
`WORKFLOW_VALIDATOR` (no private duplicate binding).

### Primary API

`validate_workflow_result(path: Path) -> WorkflowValidationResult` is the primary
non-raising path-based surface.

`validate_workflow_document(raw: dict[str, Any], *, source_path: Path) -> WorkflowValidationResult`
runs the same schema + semantic + model pipeline without reading disk.
`source_path` is required identity (not required to exist); store as given after
`Path` coercion.

`load_workflow_definition(path: Path) -> WorkflowDefinition` is a thin raising wrapper:
`FileNotFoundError` for `not_found`, `OSError` for `unreadable`, `ValueError`
otherwise.

```python
class WorkflowValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    NOT_A_FILE = "not_a_file"
    UNREADABLE = "unreadable"
    MALFORMED_YAML = "malformed_yaml"
    ROOT_NOT_MAPPING = "root_not_mapping"


class WorkflowValidationResult(BaseModel):
    status: WorkflowValidationStatus
    source_path: Path
    raw: dict[str, Any] | None
    workflow: WorkflowDefinition | None
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool: ...  # status == VALID
```

Path success: readable regular file, YAML root mapping, `workflow_v1` schema pass,
semantic pass, Pydantic map → `status=valid`, populated `raw` + `workflow`, empty
`errors`. Multi-document YAML uses the first `safe_load` document only. Empty
file / `None` root → `root_not_mapping` (no schema run).

### Error codes

| Code | Status |
|------|--------|
| `WORKFLOW_INVALID_NOT_FOUND` | `not_found` |
| `WORKFLOW_INVALID_NOT_A_FILE` | `not_a_file` |
| `WORKFLOW_INVALID_UNREADABLE` | `unreadable` |
| `WORKFLOW_INVALID_MALFORMED_YAML` | `malformed_yaml` |
| `WORKFLOW_INVALID_ROOT_NOT_MAPPING` | `root_not_mapping` |
| `WORKFLOW_INVALID_SCHEMA` | `invalid` |
| `WORKFLOW_INVALID_MODEL` | `invalid` (defensive Pydantic failure after schema) |
| `WORKFLOW_SEM_STOP_WHEN_EMPTY` | `invalid` |
| `WORKFLOW_SEM_MAX_ATTEMPTS` | `invalid` |
| `WORKFLOW_SEM_TIMEOUT` | `invalid` |
| `WORKFLOW_SEM_PATCH_LIMIT` | `invalid` |

Schema failures use one grouped error entry:

```text
Workflow schema validation failed (WORKFLOW_INVALID_SCHEMA):
- <jsonschema path>: <message>
- ...
```

Path formatting matches `SchemaValidator` (`".".join(path)` or `(root)`). On
schema failure, semantic rules do not run. IO/parse errors include absolute path
and a short Fix hint.

### Semantic rules (after schema success)

1. `WORKFLOW_SEM_MAX_ATTEMPTS` — `iteration.max_attempts >= 1`
2. `WORKFLOW_SEM_TIMEOUT` — `trigger.timeout_seconds >= 1` and
   `agent.timeout_seconds >= 1`
3. `WORKFLOW_SEM_PATCH_LIMIT` — `patch.max_files >= 1` and `patch.max_patch_kb >= 1`
4. `WORKFLOW_SEM_STOP_WHEN_EMPTY` — `len(iteration.stop_when) >= 1`

v1 requires no semantic warnings (`warnings` is always `[]`).

### Typed model

`WorkflowDefinition` covers the full V1 surface: `version`, `name`, `description`,
`trigger`, `agent`, `iteration`, `sandbox`, `approval`, `context`, `patch`.
Nested models use `extra=forbid` / strict config. `patch.reject_binary_changes`
is optional (`bool | None`) to match the schema; packaged templates may omit it.

Commands must call this API rather than ad-hoc `yaml.safe_load` + schema for
full validation. Metadata/inventory remain the lighter list layer.

## `wt workflow list`

Command entry: `getworktree.commands.workflow.command.workflow_list_command`.
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

Command entry: `getworktree.commands.workflow.command.workflow_show_command`.
Registration: `wt workflow show` under `workflow_app` in
[getworktree/cli.py](../../getworktree/cli.py).

Read-only: query workflow session by session ID and print details.

Pipeline:

1. `resolve_workflow_by_name(name, cwd=cwd)`
2. On resolve failure → error panel, exit `1` (no validate)
3. `validate_workflow_result(resolved.entry.source_path)`
4. On validate failure → error panel, exit `1` (resolve warnings may print after)
5. On success → plain-text summary, exit `0` (warnings allowed)

Pure formatters (no IO/print/exit) live in
[getworktree/core/workflows/render.py](../../getworktree/core/workflows/render.py):

- `format_workflow_show_success(workflow, *, source_path, warnings=None) -> str`
- `format_workflow_show_resolve_failure(result) -> str`
- `format_workflow_show_validate_failure(result) -> str`

### Exit codes

| Condition | Exit |
|-----------|------|
| resolve ok + validate ok (warnings allowed) | `0` |
| resolve not ok | `1` |
| validate not ok | `1` |
| unexpected internal exception | non-zero (never silent `0`) |

### Success layout

Plain text (no Rich markup), trailing newline. Header:

```text
Workflow: <name>
Source: <absolute-source-path>
Status: valid
```

or `Status: valid with warnings` plus a `Warnings:` bullet list when
`resolved.warnings + validated.warnings` is non-empty. Then sections in order:
`Description`, `Trigger`, `Agent`, `Iteration`, `Sandbox`, `Approval`,
`Context`, `Patch` (field labels/casing as in the issue / render module).
Booleans are `true`/`false`; lists use `json.dumps`; optional
`reject_binary_changes` is `null` when unset.

### Failure layout

- Exit `1`
- Rich error panel titled exactly `Workflow Show Failed`
- Resolve body: `"\n\n".join(errors)` or `Failed to resolve workflow.`
- Validate body: `"\n\n".join(errors)` or `Workflow definition is invalid.`
- No success header on failure
- If resolve warnings exist on a validate failure, print them after the panel

## Changing config or workflow shape

1. Update the relevant JSON Schema (`config_v1.json` or `workflow_v1.json`).
2. Update `CANONICAL_V1_DEFAULTS` (config) or the packaged template under
   `core/templates/workflows/*.yml` (workflows).
3. Update the corresponding Pydantic model in `core/config/models.py` or
   `core/workflows/models.py`.
4. Add/adjust tests in `tests/core/config/` or `tests/core/workflows/`.

Bump the schema version (`config_v2.json`, etc.) instead of making breaking
changes to a `v1` schema that users may already have on disk.

