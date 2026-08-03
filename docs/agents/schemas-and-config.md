# Schemas and Config

## Versioned JSON Schemas

`getworktree/schemas/config_v1.json` and `loop_v1.json` are the source of truth
for what a valid `.worktree/config.json` and loop YAML file look like. Both are
validated through `SchemaValidator` ([getworktree/common/schema_validation.py](../../getworktree/common/schema_validation.py)),
a thin wrapper over `jsonschema.Draft202012Validator` that returns a
`ValidationResult(ok, errors)` instead of raising.

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

### CLI success body

`wt config show` loads via `load_config_result`, then prints **only** the
serialized JSON body on success (exit `0`). No source-path / validation header
in this command surface yet. On non-ok load it prints `ConfigLoadResult.errors`
(error panel) and exits `1` without emitting partial JSON. Show never creates or
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

