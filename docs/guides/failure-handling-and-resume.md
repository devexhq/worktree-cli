# Failure Handling & Session Resumption

Worktree provides robust error recovery, declarative quality assertions, and durable session checkpoints so that long-running workflows can recover gracefully from failures.

---

## Failure Handling Policies (`on_failure`)

Each step (or blueprint `defaults:`) can specify an `on_failure` directive to control execution flow when a step encounters an error or fails an assertion.

### Policy Vocabulary

| Policy | Behavior |
|---|---|
| `abort` *(default)* | Terminates execution immediately and marks the session as failed. |
| `continue` | Ignores the step failure, marks the step as ignored, and proceeds to the next step. |
| `retry` | Retries the step locally up to `max_retries` attempts before escalating to `on_max_retries`. |
| `prompt_user` | Prompts the user interactively in the terminal to choose: Retry, Continue, or Abort. |

---

## Configuring `on_failure`

You can supply a bare policy name or a detailed retry specification:

### 1. Simple String Shorthand

```yaml
steps:
  - id: lint
    run: ruff check .
    on_failure: continue
```

### 2. Detailed Retry & Escalation Object

```yaml
steps:
  - id: download-dependencies
    run: uv sync
    on_failure:
      action: retry
      max_retries: 3
      backoff_ms: 1000
      on_max_retries: prompt_user
```

*Note: `on_max_retries` must be a terminal policy (`abort`, `continue`, or `prompt_user`).*

---

## Step Quality Assertions (`assert:`)

Steps can declare criteria that must pass for the step to be considered successful. If an assertion fails, the step is marked as failed even if the process exited with code `0`.

```yaml
steps:
  - id: run-pytest
    name: Verify test results
    run: pytest --json-report --json-report-file=report.json
    assert:
      exit_code: 0
      output_contains: "0 errors"
      output_not_contains: ["FATAL", "PANIC"]
      regex_match: "([0-9]+) passed"
      json_match:
        path: "summary.status"
        operator: "eq"
        value: "APPROVED"
      file_exists: "report.json"
      file_not_empty: "report.json"
```

For full details on assertion operators, see the [Assertions Schema Reference](../reference/assertions-schema.md).

---

## Interactive Prompts & Durable Checkpoints

When a step fails with `on_failure: prompt_user`:
1. Worktree pauses the execution loop.
2. A durable **session checkpoint** is persisted in `.worktree/data.db`.
3. The user is prompted interactively:
   ```text
   Step 'verify-tests' failed (exit code: 1).
   [r]etry / [c]ontinue / [a]bort ?
   ```

### Checkpoint Contents
The checkpoint preserves:
- The sandbox branch, path, and base commit.
- Completed step outputs and execution logs.
- Resolved parameter input values.
- The index of the pending step.

---

## Resuming Sessions (`wt resume`)

If you exit or interrupt an interactive session (or if a prompt is left unresolved), the sandbox remains preserved. You can resume execution from the exact point of failure using `wt resume`:

```bash
# Resume by session ID
wt resume workflow_a1b2c3d4
```

Worktree will reload the sandbox and re-execute the pending step without re-running earlier completed steps.

---

## Non-Interactive & CI/CD Execution

In automated environments (such as CI pipelines or background cron jobs), interactive prompts cannot block on standard input.

Pass the `--non-interactive` flag:

```bash
wt run test-suite --non-interactive
```

When `--non-interactive` is enabled, any `prompt_user` policy automatically degrades to `abort` and emits a warning.

---

## Next Steps

- Check out the [AI Agent Providers Guide](agent-providers.md).
- Read the [Assertions Schema Reference](../reference/assertions-schema.md).
