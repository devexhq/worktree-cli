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

`core/config/manager.py` loads and re-validates the file at runtime into typed
`WorktreeConfig`/`WorktreeContext` Pydantic models and surfaces developer warnings
(e.g. missing agent model, running on `main`/`master`, unusually high sandbox limits).

## Changing config or loop shape

1. Update the relevant JSON Schema (`config_v1.json` or `loop_v1.json`).
2. Update `CANONICAL_V1_DEFAULTS` (config) or the packaged template under
   `core/templates/loops/*.yml` (loops).
3. Update the corresponding Pydantic model in `core/config/manager.py`.
4. Add/adjust tests in `tests/core/config/` or `tests/core/loops/`.

Bump the schema version (`config_v2.json`, etc.) instead of making breaking
changes to a `v1` schema that users may already have on disk.
