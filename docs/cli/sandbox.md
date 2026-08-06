# `wt sandbox`

The `wt sandbox` command provisions and manages isolated Git worktrees to allow AI agents or human developers to run experiments safely.

## Subcommands

### `wt sandbox list`

List all active sandboxes associated with the current project repository:

```bash
wt sandbox list
```

### `wt sandbox create`

Create a new isolated Git worktree:

```bash
wt sandbox create my-feature
```

### `wt sandbox show`

Inspect sandbox details, path, branch, and status:

```bash
wt sandbox show my-feature
```

### `wt sandbox delete`

Remove an isolated worktree sandbox when work is complete:

```bash
wt sandbox delete my-feature
```
