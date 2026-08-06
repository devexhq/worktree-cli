# `wt task`

The `wt task` command manages bounded, single-shot actions such as linting, formatting, audit logging, or prompt generation.

## Subcommands

### `wt task list` (Default)

Running `wt task` (or `wt task list`) displays available task blueprints and recent execution history:

```bash
wt task
```

### `wt task show`

Inspects a specific task blueprint:

```bash
wt task show audit-tokens
```

### `wt task run`

Executes a bounded task:

```bash
wt task run audit-tokens
```

## Default Subcommand Behavior

Executing `wt task` without subcommands automatically defaults to running `wt task list`.
