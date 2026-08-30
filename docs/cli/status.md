# `wt status`

The `wt status` command displays the health and status of the current Worktree workspace, active Git branch, config validity, active sandboxes capacity, and catalog inventory.

## Usage

```bash
wt status
```

## Description

`wt status` provides a scannable dashboard showing:
- **Project Name**: Name of the configured worktree project.
- **Config Status**: Validation status and relative path to `.worktree/config.json`.
- **Active Git Branch**: Current Git branch (with dirty indicator if uncommitted changes exist).
- **Agent Model**: Configured agent model name.
- **Active Sandboxes**: Active sandboxes count and concurrency ceiling (`active / max max`).
- **Catalog Items**: Total valid blueprints and inventory breakdown (`valid / total`).
- **Warnings**: Actionable developer and workspace configuration warnings.

## Examples

```bash
wt status
```

Sample output:

```text
Worktree Workspace Status
┌──────────────────────┬─────────────────────────────┐
│ Property             │ Value                       │
├──────────────────────┼─────────────────────────────┤
│ Project Name         │ worktree-cli                │
│ Config Status        │ ok (.worktree/config.json)  │
│ Active Git Branch    │ feature/status-cmd          │
│ Agent Model          │ gemini-2.5-flash            │
│ Active Sandboxes     │ 1 / 5 max                   │
│ Catalog Items        │ 2 valid / 2 total           │
└──────────────────────┴─────────────────────────────┘

⚠️ Configuration & Context Warnings:
  • max_active_sandboxes (10) is unusually high.
```

