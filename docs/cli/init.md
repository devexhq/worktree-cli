# `wt init`

The `wt init` command initializes a project repository for Worktree (`wt`), provisioning the `.worktree/` directory structure, a stable project identity, canonical configuration defaults, a local `.worktree/.gitignore`, the state database, and blueprint catalog folders.

## Usage

```bash
wt init [OPTIONS]
```

## Options

| Flag | Description |
| --- | --- |
| `--id <ID>` | Explicit unique project ID slug. Must match `^[a-z0-9][a-z0-9-_]{2,62}$`; an invalid value exits with code `2`. When omitted, a friendly slug is generated. |
| `--display-name <NAME>` | Human-readable project display name. |
| `--force` | Overwrite an existing `project.json`'s id when `--id` is also provided. Has no effect on its own, and never touches `config.json`. |
| `--format <terminal\|json>` | Presentation format (`terminal` or `json`). Defaults to `terminal`. |
| `--repair` | Add missing required config keys without overwriting user values. |
| `--overwrite` | Replace an existing config with fresh V1 defaults (destructive). |

### `--id` / `--display-name` / `--force`

`wt init` writes `<repo>/.worktree/project.json` containing a stable project identity (`id`, `display_name`, `created_at`). Without `--id`, a generated slug (e.g. `brave-otter`) is used. Rerunning `wt init` preserves an existing identity unless both `--id` and `--force` are passed together, in which case the identity is overwritten with the new `--id`. `--force` alone, without `--id`, has no effect on an existing identity or on `config.json`.

```bash
wt init --id my-project --display-name "My Project"
wt init --id my-project --force   # only effective on a rerun that changes the id
```

### `.worktree/.gitignore`

`wt init` pre-seeds `<repo>/.worktree/.gitignore`, scoping the local ignore rules to `.worktree/` itself rather than the repository root `.gitignore`. See `WORKTREE_LOCAL_GITIGNORE_ENTRIES` for the exact tracked and ignored entries; the repository-root `.gitignore` is never modified by `wt init`.

### `--repair`

Non-destructively repairs an existing configuration file. It scans `.worktree/config.json` and inserts any missing schema keys using default V1 canonical values, preserving your existing user configurations and initialization timestamps.

```bash
wt init --repair
```

### `--overwrite`

Destructively overwrites an existing `.worktree/config.json` file with fresh canonical V1 defaults. Does not affect the project identity in `project.json`.

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

### Initializing with an explicit project id

```bash
wt init --id my-project --display-name "My Project"
```

### Repairing schema drift after updating `wt`

```bash
wt init --repair
```

### JSON structured output

```bash
wt init --id my-project --format json
```

Emits a structured NDJSON payload (see `WorkspaceInitView` for the full field list):

```json
{"event_type": "WorkspaceInitResult", "payload": {"ok": true, "root_path": "/path/to/my-repo/.worktree", "root_path_relative": ".worktree", "bootstrap_outcome": "initialized", "dirs_created": [".worktree/.meta"], "project_id": "my-project", "identity_path_relative": ".worktree/project.json", "identity_preserved": false, "gitignore_path_relative": ".worktree/.gitignore", "gitignore_tracked_entries": ["config.json", "project.json", "catalog/"], "config_created": true, "config_overwritten": false, "config_repaired": false, "config_skipped_existing": false, "config_path_relative": ".worktree/config.json", "inserted_keys": [], "seeded_files": [".worktree/catalog/blueprints/wt/fix-tests.yml", ".worktree/catalog/blueprints/wt/review-fix.yml"], "skipped_seed_files": [], "overwritten_seed_files": [], "failure_mode": null, "errors": [], "warnings": [], "fixes": []}}
```
