# `wt init`

The `wt init` command initializes a project repository for Worktree (`wt`), provisioning the `.worktree/` directory structure, canonical configuration defaults, state database, and blueprint catalog folders.

## Usage

```bash
wt init [OPTIONS]
```

## Options

| Flag | Description |
| --- | --- |
| `--format <terminal\|json>` | Presentation format (`terminal` or `json`). Defaults to `terminal`. |
| `--repair` | Add missing required config keys without overwriting user values. |
| `--overwrite` | Replace an existing config with fresh V1 defaults (destructive). |

### `--repair`

Non-destructively repairs an existing configuration file. It scans `.worktree/config.json` and inserts any missing schema keys using default V1 canonical values, preserving your existing user configurations and initialization timestamps.

```bash
wt init --repair
```

### `--overwrite`

Destructively overwrites an existing `.worktree/config.json` file with fresh canonical V1 defaults.

```bash
wt init --overwrite
```

### `--format`

Specifies the output presentation format. When set to `json`, emits structured NDJSON envelopes suitable for desktop and UI integrations.

```bash
wt init --format json
```

## Examples

### Initializing a new repository

```bash
cd /path/to/my-repo
wt init
```

### Repairing schema drift after updating `wt`

```bash
wt init --repair
```

### JSON structured output

```bash
wt init --format json
```

Emits a structured NDJSON payload:

```json
{"event_type": "InitCommandOutcome", "payload": {"bootstrap_result": {"root_path": "/path/to/my-repo/.worktree", "root_created": true, "dirs_created": ["/path/to/my-repo/.worktree/sessions", "/path/to/my-repo/.worktree/artifacts", "/path/to/my-repo/.worktree/tmp", "/path/to/my-repo/.worktree/logs", "/path/to/my-repo/.worktree/.meta", "/path/to/my-repo/.worktree/workflows"], "dirs_existing": [], "repaired": false, "warnings": [], "errors": [], "seed_result": {"created_files": [], "skipped_existing_files": [], "overwritten_files": [], "warnings": [], "errors": []}}, "config_result": {"created": true, "skipped_existing": false, "repaired": false, "overwritten": false, "inserted_keys": [], "config_path": "/path/to/my-repo/.worktree/config.json", "warnings": [], "errors": []}, "seed_result": {"created_files": ["/path/to/my-repo/.worktree/catalog/workflows/wt/fix-tests.yml", "/path/to/my-repo/.worktree/catalog/workflows/wt/review-fix.yml"], "skipped_existing_files": [], "overwritten_files": [], "warnings": [], "errors": []}, "errors": []}}
```

