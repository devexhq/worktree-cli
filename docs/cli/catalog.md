# `wt catalog`

The `wt catalog` command manages project blueprint templates for workflows, tasks, and agents.

## Subcommands

### `wt catalog list`

List all catalog items synchronized from local blueprint templates:

```bash
wt catalog list
```

Filtered list by blueprint type:

```bash
wt catalog list --type task
wt catalog list --type workflow
```

### `wt catalog create`

Scan local directories and register new catalog blueprint templates into SQLite database storage (`.worktree/data.db`):

```bash
wt catalog create
```
