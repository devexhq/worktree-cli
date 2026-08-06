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
wt catalog
```

#### Options

* `--type [workflow|task|step]`: Filter blueprints by item type.

```bash
# List workflow blueprints
wt catalog list --type workflow

# List task blueprints
wt catalog list --type task

# List step blueprints
wt catalog list --type step
```

### `wt catalog create`

Creates a new blueprint template file in `.worktree/catalog/<type>s/<name>.yml` and registers it in SQLite:

```bash
wt catalog create <type> --name <name> [OPTIONS]
```

#### Arguments

- `type`: Blueprint type (`workflow`, `task`, `step`).

#### Options

- `--name TEXT`: Unique blueprint name (required).
- `--template TEXT`: Optional built-in template name to pre-populate content from.

#### Examples

```bash
# Create a new workflow blueprint from the built-in feature-dev template
wt catalog create workflow --name my-feature --template feature-dev

# Create a new custom task blueprint
wt catalog create task --name format-code
```

### `wt catalog show`

Displays definition content and metadata for a specific catalog blueprint:

```bash
wt catalog show <sha_or_name>
```

### `wt catalog delete`

Deletes a catalog blueprint file and unregisters its record from the database:

```bash
wt catalog delete <sha_or_name> [OPTIONS]
```

#### Options

- `--force`: Skip confirmation prompt.

```bash
wt catalog delete my-feature --force
```
