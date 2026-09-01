# `wt sandbox`

The `wt sandbox` command provisions and manages isolated Git worktrees to allow AI agents or human developers to run experiments safely.

## Subcommands

### `wt sandbox list`

List all active sandboxes associated with the current project repository:

```bash
wt sandbox list [--format terminal|json]
```

### `wt sandbox create`

Create a new isolated Git worktree:

```bash
wt sandbox create [--name <name>] [--base-ref <ref>] [--wip/--no-wip] [--format terminal|json]
```

### `wt sandbox show`

Inspect sandbox details, path, branch, and status:

```bash
wt sandbox show <sandbox-id> [--format terminal|json]
```

### `wt sandbox prune`

Safely prune stale sandboxes, orphaned directories, and temporary branches:

```bash
wt sandbox prune [--dry-run] [--force] [--format terminal|json]
```

### `wt sandbox delete`

Remove an isolated worktree sandbox when work is complete:

```bash
wt sandbox delete <sandbox-id> [--force] [--format terminal|json]
```

### `wt sandbox apply`

Apply changes from an isolated sandbox worktree back into the main workspace:

```bash
wt sandbox apply <sandbox-id> [OPTIONS]
```

#### Options

| Flag | Description |
| --- | --- |
| `--strategy <patch\|squash>` | Strategy for applying changes: `patch` (default: uncommitted working tree changes) or `squash` (stages and creates a single Git commit). |
| `--allow-dirty` | Allow application even if the main workspace has uncommitted changes. |
| `--dry-run` | Perform pre-apply conflict checks without modifying the workspace. |
| `--delete`, `-d` | Delete the sandbox worktree and branch upon successful application. |
| `--message <msg>`, `-m <msg>` | Custom commit message when using `--strategy squash`. |
| `--format <terminal\|json>` | Presentation format (`terminal` or `json`). |

#### Examples

Apply changes as working tree modifications:
```bash
wt sandbox apply sbx_8f2a1b9c
```

Apply and squash into a commit, then remove the sandbox:
```bash
wt sandbox apply sbx_8f2a1b9c --strategy squash --message "feat: implement auth service" --delete
```

### `wt sandbox diff`

Inspect differences between the sandbox worktree and its base commit:

```bash
wt sandbox diff <sandbox-id> [OPTIONS]
```

#### Options

| Flag | Description |
| --- | --- |
| `--stat` | Output summary diffstat statistics (files changed, insertions, deletions) instead of the full unified diff. |
| `--format <terminal\|json>` | Presentation format (`terminal` or `json`). |

#### Examples

View unified diff:
```bash
wt sandbox diff sbx_8f2a1b9c
```

View diffstat summary:
```bash
wt sandbox diff sbx_8f2a1b9c --stat
```


