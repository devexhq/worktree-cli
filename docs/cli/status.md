# `wt status`

The `wt status` command displays the health and status of the current Worktree workspace, active Git worktree sandboxes, database health, and workflow session metrics.

## Usage

```bash
wt status
```

## Description

`wt status` provides a scannable dashboard showing:
- **Workspace path**: Resolved `.worktree/` directory path.
- **Config health**: Validation status of `.worktree/config.json`.
- **Database status**: Path to `.worktree/data.db` and stored session counts.
- **Active sandboxes**: Active Git worktrees (`wt/` branches) and lifecycle state (`active`, `merged`, `cleaned`, `conflict`).
- **Workflow history**: Summary of recent workflow run sessions and completion rates.

## Examples

```bash
wt status
```

Sample output:

```text
Worktree Workspace Status
  Root Path: /path/to/my-repo/.worktree
  Config:    VALID (v1)
  Database:  /path/to/my-repo/.worktree/data.db (OK)

Sandboxes:
  - wt/feature-dev (active) -> .worktree/sandboxes/feature-dev

Workflows:
  - 3 total sessions recorded
```
