# `wt workflow`

The `wt workflow` command discovers, lists, and validates workflow definitions.

> **Status:** `wt workflow run` and `wt workflow resume` currently only load and
> validate a workflow definition — they do not execute any steps yet. Step
> execution is being rebuilt incrementally on top of the Workflow Spec v1
> model; see
> [docs/agents/architecture.md](../agents/architecture.md#workflow-run-cli-not-yet-executing-workflows)
> and issues [#171](https://github.com/getworktree/getworktree/issues/171),
> [#172](https://github.com/getworktree/getworktree/issues/172), and
> [#173](https://github.com/getworktree/getworktree/issues/173).

## Subcommands

### `wt workflow` / `wt workflow list`

Lists recorded workflow sessions and available catalog workflow blueprints. Executing `wt workflow` without subcommands defaults to listing workflows.

```bash
wt workflow
```

### `wt workflow show`

Displays the session details and execution status of a specific workflow run session:

```bash
wt workflow show <session_id>
```

### `wt workflow run`

Validates a workflow definition by name. Execution is not implemented yet: on
a valid definition the command prints an error panel and exits `1`.

```bash
wt workflow run <name>
```

#### Arguments

* `name`: Logical workflow name registered in catalog storage or built-in templates.

### `wt workflow resume`

Resumes an interrupted or paused workflow session:

```bash
wt workflow resume <session_id>
```

---

## Workflow YAML Definition Schema

Workflow blueprints live in `.worktree/workflows/<name>.yml` (see
`paths.workflows_dir` in [config](../getting-started/configuration.md)). Below
is an example matching the current Workflow Spec v1 schema
(`getworktree/schemas/v1/workflow.json`):

```yaml
version: "1.0"
name: "fix-tests"
description: "Iteratively fix failing tests until they pass or attempts are exhausted"
timeout_seconds: 600

steps:
  - id: dev-cycle
    type: loop
    max_iterations: 5
    until:
      - "steps.run-tests.exit_code == 0"
    on_max_iterations: prompt_user
    do:
      - id: run-tests
        run: pytest
        on_failure: continue

      - id: ai-fix
        uses: wt/ai-code-patcher
        on_failure: abort
```

### Workflow Configuration Sections

| Key | Description |
| --- | --- |
| `version` | Must be `1` or `"1.0"`. |
| `name` | Required; workflow identifier (defaults `id` to `name` if omitted). |
| `description` | Optional human-readable summary. |
| `timeout_seconds` | Optional overall workflow timeout (`>= 1`). |
| `env` | Optional environment variables map. |
| `inputs` | Optional named input declarations (`description`, `required`, `default`). |
| `steps` | List of standard steps (`uses`/`run`, mutually exclusive) and/or `loop` blocks (`max_iterations`, `until`, `do`, `on_max_iterations`). |

### `on_failure`

Each standard step's `on_failure` accepts either a bare policy string or a configurable object:

```yaml
# Bare string form
on_failure: abort   # abort | continue | prompt_user | retry

# Object form (retry tuning + post-retry escalation)
on_failure:
  action: retry
  max_retries: 3
  backoff_ms: 500
  on_max_retries: abort   # abort | continue | prompt_user (no retry-on-retry)
```

`on_max_iterations` on `loop` blocks is always a bare string (`abort`, `continue`, or
`prompt_user` — `retry` is not valid there).

