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

### Healthy workspace output

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

### Uninitialized workspace output

When `.worktree/config.json` is missing or the workspace is uninitialized:

```text
Worktree Workspace Status (Uninitialized)
┌──────────────────────┬────────────────────────────────────────┐
│ Property             │ Value                                  │
├──────────────────────┼────────────────────────────────────────┤
│ Project Name         │ [dim]Uninitialized[/dim]               │
│ Config Status        │ [yellow]CONFIG_NOT_FOUND[/yellow]         │
│ Active Git Branch    │ main                                   │
│ Agent Model          │ [dim]Not Configured[/dim]               │
│ Active Sandboxes     │ [dim]N/A[/dim]                         │
│ Catalog Items        │ [dim]N/A[/dim]                         │
└──────────────────────┴────────────────────────────────────────┘

⚠️ Configuration & Context Warnings:
  • Worktree workspace is not initialized. Run 'wt init' to configure.

Next Steps & Remediation:
  • Run 'wt init' to initialize Worktree in this repository.
```

### Degraded workspace output

When `config.json` is malformed, invalid, or run outside a Git repository:

```text
Worktree Workspace Status (Degraded)
┌──────────────────────┬────────────────────────────────────────┐
│ Property             │ Value                                  │
├──────────────────────┼────────────────────────────────────────┤
│ Project Name         │ [dim]Uninitialized[/dim]               │
│ Config Status        │ [red]CONFIG_MALFORMED_JSON[/red]       │
│ Active Git Branch    │ main                                   │
│ Agent Model          │ [dim]Not Configured[/dim]               │
│ Active Sandboxes     │ [dim]N/A[/dim]                         │
│ Catalog Items        │ [dim]N/A[/dim]                         │
└──────────────────────┴────────────────────────────────────────┘

⚠️ Configuration & Context Warnings:
  • Malformed config.json: Expecting property name enclosed in double quotes (line 2 col 1)

Next Steps & Remediation:
  • Repair JSON syntax in .worktree/config.json or restore from backup.
```


