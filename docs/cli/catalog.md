# `wt catalog`

The `wt catalog` command manages project blueprint templates for workflows, tasks, and steps. Catalog blueprints are stored as YAML files under `.worktree/catalog/` and indexed into the centralized SQLite database, scoped to this project.

## Auto-sync

`wt catalog list`, `wt catalog show`, `wt catalog delete`, and `wt catalog validate <catalog-name>` all re-synchronize the SQLite index against `.worktree/catalog/` before resolving their target, so a lookup always reflects files added, edited, or removed on disk since the last run — there is no separate sync step to run first. `wt catalog create` indexes the new file it just wrote. The one exception is `wt catalog validate <file-path>`: validating a direct file path is read-only and never touches the index.

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

Lists catalog blueprints indexed in the centralized database for this project. Executing `wt catalog` without subcommands defaults to listing blueprints.

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

Deletes a catalog blueprint file and unregisters its record from the database. Bundled templates in the `wt/` namespace (e.g. `wt/starter-task`, `wt/fix-tests`) are protected and cannot be deleted:

```bash
wt catalog delete <sha_or_name> [OPTIONS]
```

#### Options

- `--force`: Skip confirmation prompt.
- `--format [terminal|json]`: Presentation format (`terminal` or `json`).

```bash
wt catalog delete my-feature --force
```

### `wt catalog validate`

Validates a catalog blueprint or step definition (YAML syntax, schema, and semantic invariants such as duplicate step IDs, undeclared input placeholders, and unsafe `script_path` values) without executing it:

```bash
wt catalog validate <target> [--type blueprint|step] [--format terminal|json]
```

#### Arguments

- `target`: A catalog item name or namespaced identifier (e.g. `commit-plan`, `wt/fix-tests`), or a relative/absolute file path.

#### Options

- `--type [blueprint|step]`: The item type to validate `target` against. Required only when `target` resolves to a file path rather than an indexed catalog name — a file has no catalog record to read the type from. Ignored for a catalog-name target, since the item type is already known from the matched record.
- `--format [terminal|json]`: Presentation format (`terminal` or `json`).

#### Exit codes

- `0`: Validation passed (warnings permitted).
- `1`: Validation failed (YAML syntax error, schema violation, or a broken invariant such as a duplicate step ID or unsafe `script_path`).
- `2`: Validation could not run at all — the target was not found, the file was unreadable, or a file target was given without the required `--type`.

```bash
# Validate an indexed blueprint by catalog name
wt catalog validate commit-plan

# Validate a step file not yet indexed in the catalog
wt catalog validate .worktree/catalog/steps/run-pytest.yml --type step

# Output structured NDJSON envelope
wt catalog validate commit-plan --format json
```
