# `wt catalog`

The `wt catalog` command manages project blueprint templates for workflows, tasks, and steps. Catalog blueprints are stored as YAML files under `.worktree/catalog/` and indexed into the SQLite database (`.worktree/data.db`).

## Catalog Directory Structure

```text
.worktree/catalog/
├── workflows/
│   └── fix-tests.yml
├── tasks/
│   └── audit-tokens.yml
└── steps/
    └── run-pytest.yml
```

---

## Subcommands

### `wt catalog` / `wt catalog list` (Default)

Lists catalog blueprints indexed in `.worktree/data.db`. Executing `wt catalog` without subcommands defaults to listing blueprints.

```bash
wt catalog [--type <type>] [--format terminal|json]
```

#### Options

* `--type [workflow|task|step|template]`: Filter blueprints by item type. `--type template` lists the packaged `default.yml` blueprint scaffolds instead of querying the database.
* `--format [terminal|json]`: Presentation format (`terminal` or `json`).

```bash
# List workflow blueprints
wt catalog list --type workflow

# List task blueprints
wt catalog list --type task

# List step blueprints
wt catalog list --type step

# List packaged default.yml templates
wt catalog list --type template

# Output structured NDJSON envelope
wt catalog list --format json
```

### `wt catalog create`

Creates a new blueprint template file in `.worktree/catalog/<type>s/<name>.yml` and registers it in SQLite:

```bash
wt catalog create <type> --name <name> [--format terminal|json]
```

#### Arguments

- `type`: Blueprint type (`workflow`, `task`, `step`).

#### Options

- `--name TEXT`: Unique blueprint name (required).
- `--format [terminal|json]`: Presentation format (`terminal` or `json`).

#### Examples

```bash
# Create a new workflow blueprint (seeded from the packaged default.yml scaffold)
wt catalog create workflow --name my-feature

# Create a new custom task blueprint
wt catalog create task --name format-code
```

### `wt catalog show`

Displays definition content and metadata for a specific catalog blueprint. If `<sha_or_name>` is not indexed in the database, falls back to packaged templates under `core/catalog/templates/` (e.g. `default`, or curated names like `fix-tests`):

```bash
wt catalog show <sha_or_name> [--format terminal|json]
```

#### Options

- `--format [terminal|json]`: Presentation format (`terminal` or `json`).

### `wt catalog delete`

Deletes a catalog blueprint file and unregisters its record from the database:

```bash
wt catalog delete <sha_or_name> [OPTIONS]
```

#### Options

- `--force`: Skip confirmation prompt.
- `--format [terminal|json]`: Presentation format (`terminal` or `json`).

```bash
wt catalog delete my-feature --force
```
