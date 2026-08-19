# `wt history`

The `wt history` command inspects past blueprint executions (tasks and workflows), enabling developers to filter past runs and view granular step details, error messages, and checkpoint data.

## Usage

```bash
wt history [OPTIONS]
```

### Options

| Flag | Description |
| --- | --- |
| `--limit, -l <int>` | Maximum number of history records to display (default: 20). |
| `--status, -s <status>` | Filter runs by lifecycle status (`running`, `completed`, `failed`, `cancelled`, `paused`). |
| `--kind, -k <kind>` | Filter runs by blueprint kind (`task`, `workflow`). |

## Subcommands

### `wt history show`

Show granular metadata, error details, and checkpoint contents for a specific execution session.

```bash
wt history show <session_id>
```

#### Arguments

| Argument | Description |
| --- | --- |
| `session_id` | Required session identifier to inspect. |

## Examples

List recent blueprint execution history:

```bash
wt history
```

List failed executions limited to the 5 most recent runs:

```bash
wt history --status failed --limit 5
```

List workflow executions only:

```bash
wt history --kind workflow
```

Inspect details for a specific session:

```bash
wt history show task_a1b2c3d4
```
