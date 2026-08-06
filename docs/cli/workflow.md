# `wt workflow`

The `wt workflow` command manages autonomous AI workflows following a **Plan → Execute → Verify** loop cycle.

## Subcommands

### `wt workflow list`

Lists available workflows registered in your catalog or local database.

```bash
wt workflow list
```

### `wt workflow show`

Displays the configuration and steps of a specific workflow blueprint:

```bash
wt workflow show fix-tests
```

### `wt workflow run`

Executes a workflow in an isolated environment:

```bash
wt workflow run fix-tests --max-attempts 5
```

## Workflow Execution Loop

During execution, `wt workflow`:

1. Creates an isolated iteration workspace.
2. Formulates a plan using configured LLM providers.
3. Applies code modifications and runs verification suites (`pytest`, `inv test`).
4. Persists execution state and session history to `.worktree/data.db`.
