# Schemas and Config

## Versioned JSON Schemas

`getworktree/schemas/config_v1.json` and `loop_v1.json` are the source of truth
for what a valid `.worktree/config.json` and loop YAML file look like. Both are
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
- Top-level `required`: `version`, `project`, `paths`, `sandbox`, `loop`,
  `agent`, `patch`, `approval`, `history`, `doctor`, `prune`, `telemetry`.
- `version` is integer `const: 1`.

Enums (exact tokens):

- `agent.provider`: `local` | `openai` | `anthropic` | `azure_openai` | `custom`
- `patch.strategy`: `unified_diff`

Notable bounds / string rules:

- Path strings (`paths.*`, `sandbox.base_ref`): non-empty (`minLength: 1`)
- Positive integers (`minimum: 1`): sandbox/loop attempt and timeout fields,
  `agent.max_tokens`, `patch.max_files` / `max_patch_kb`, `history.max_sessions`
- `agent.temperature`: number in `[0, 2]`
- `prune.artifact_ttl_days`: integer `minimum: 0`
- `agent.model` / `agent.endpoint`: `string | null`; non-null strings must be
  non-empty
- `project.name` / `project.initialized_at`: `string | null` (loader maps null
  name to `"unnamed_project"` after schema validation)

Not expressed in the JSON Schema (validator-engine / runtime territory):

- Cross-field limits (e.g. `loop.default_max_attempts <= max_attempts_hard_limit`)
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
`WorktreeConfig` (full V1 surface: version, project, paths, sandbox, loop, agent,
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

## Config serialization and `wt config show`

Runtime display of configuration uses the full V1 surface after model defaults
and load normalizations (not a sparse dump of on-disk keys).

Helpers in
[getworktree/core/config/serialize.py](../../getworktree/core/config/serialize.py):

- `serialize_config(config: WorktreeConfig) -> dict` — plain dict, no I/O, no
  print/exit; top-level key order is
  `version`, `project`, `paths`, `sandbox`, `loop`, `agent`, `patch`,
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

## Changing config or loop shape

1. Update the relevant JSON Schema (`config_v1.json` or `loop_v1.json`).
2. Update `CANONICAL_V1_DEFAULTS` (config) or the packaged template under
   `core/templates/loops/*.yml` (loops).
3. Update the corresponding Pydantic model in `core/config/models.py`.
4. Add/adjust tests in `tests/core/config/` or `tests/core/loops/`.

Bump the schema version (`config_v2.json`, etc.) instead of making breaking
changes to a `v1` schema that users may already have on disk.

