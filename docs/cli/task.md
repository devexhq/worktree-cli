# `wt task`

The `wt task` command manages bounded, single-shot execution blueprints such as linting, auditing, formatting, or automated prompt actions.

## Subcommands

### `wt task` / `wt task list` (Default)

Lists recorded task run history. Task blueprints themselves are managed via
`wt catalog`. Running `wt task` without subcommands defaults to `wt task list`:

```bash
wt task
```

### `wt task show`

Inspects a specific task blueprint definition and metadata:

```bash
wt task show <name>
```

### `wt task run`

Executes a bounded task blueprint:

```bash
wt task run <name>
wt task run <name> --non-interactive
```

#### Options

| Flag | Description |
| --- | --- |
| `--no-sandbox` | Run in-place without a Git sandbox. |
| `--keep` | Retain the sandbox worktree after completion. |
| `--agent` | Override the default target agent adapter. |
| `--non-interactive` | Disable interactive failure prompts. Steps with `on_failure: prompt_user` abort with a warning instead of blocking on stdin. Also applies when stdin is not a TTY. |

When a step fails with effective terminal policy `prompt_user` and the run is
interactive, the CLI prompts:

```text
Step 'create-plan' failed (exit code 1).
<details>

Task paused waiting for user input.

Options:
  [r] Retry step execution
  [c] Continue run (ignore failure)
  [a] Abort run

Select option [r/c/a]:
```

Choices accept short letters or full words (`retry` / `continue` / `abort`).
Invalid input re-prompts. For a tracked task session the runtime persists
`status=paused` and a checkpoint JSON payload before waiting. There is no
`wt task resume` command; paused task rows are stored for the same checkpoint
shape as workflows. Non-interactive runs abort `prompt_user` and never leave
the task `paused`.

#### Examples

```bash
wt task run audit-tokens
wt task run format-code
wt task run audit-tokens --non-interactive
```

---

## Task Blueprint YAML Schema

Task blueprints live in `.worktree/catalog/tasks/<name>.yml`.

```yaml
name: audit-tokens
description: Scan project files for hardcoded API keys and token strings
use_sandbox: true

defaults:
  on_failure: continue

steps:
  - command: python -m scripts.audit_tokens
  - id: publish-report
    run: ./scripts/publish_report.sh
    on_failure: abort   # explicit step value wins over defaults
```

### Task Definition Properties

| Property | Type | Description |
| --- | --- | --- |
| `name` | string | Unique task blueprint name (required). |
| `description` | string | Human-readable explanation of what the task performs. |
| `summary` | string | Optional short summary. |
| `use_sandbox` | boolean | Whether the task runs in a sandbox (default: `true`). |
| `inputs` | object | Optional named parameter inputs. |
| `defaults` | object | Optional blueprint defaults. Currently only `defaults.on_failure` (bare policy string or full failure object). Fills steps that omit `on_failure`; explicit step values win unchanged. |
| `steps` | list | Ordered `StepDefinition` entries (`run` / `uses` / inline `type`). |

### `defaults.on_failure`

Same shape as step-level `on_failure`:

```yaml
defaults:
  on_failure: continue

# or
defaults:
  on_failure:
    action: retry
    max_retries: 5
    backoff_ms: 200
    on_max_retries: prompt_user
```

Resolution is fill-if-omitted only at load time. It is not a second task-level
escalation ladder after steps run.
