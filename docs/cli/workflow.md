# `wt workflow`

The `wt workflow` command manages autonomous AI workflows following a **Plan → Execute → Verify** loop cycle.

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

Executes an autonomous workflow loop in an isolated Git worktree sandbox:

```bash
wt workflow run <name> [OPTIONS]
```

#### Arguments

* `name`: Logical workflow blueprint name registered in catalog storage or built-in templates.

#### Options

* `--max-attempts INTEGER`: Override maximum loop attempts (>= 1).
* `--keep / --no-keep`: Retain the sandbox worktree upon completion (overrides `auto_clean`).
* `--approve-each / --no-approve-each`: Require explicit user confirmation before applying patch diffs.
* `--wip / --no-wip`: Include uncommitted working-tree changes in the sandbox workspace.
* `--dump-prompt / --no-dump-prompt`: Debugging aid to dump LLM prompt payloads to `/tmp`.

```bash
# Run a test fixing workflow with custom max attempts and WIP changes
wt workflow run fix-tests --max-attempts 5 --wip
```

### `wt workflow resume`

Resumes an interrupted or paused workflow session:

```bash
wt workflow resume <session_id>
```

---

## Workflow YAML Definition Schema

Workflow blueprints live in `.worktree/catalog/workflows/<name>.yml`. Below is the complete schema specification:

```yaml
name: fix-tests
description: Autonomous test remediation loop

trigger:
  command: pytest
  args: ["-q"]
  timeout_seconds: 120

agent:
  provider: gemini
  mode: fix_failure
  timeout_seconds: 300

iteration:
  max_attempts: 3
  stop_when:
    - trigger_passes
    - unfixable

sandbox:
  auto_clean: true
  keep_on_failure: true

approval:
  require_before_apply: false

context:
  include:
    - trigger_output
    - changed_files

patch:
  strategy: unified_diff

steps:
  # 1. Inline Command Step
  - name: lint-check
    type: command
    command: ruff check .
    timeout_seconds: 60
    failure_action: abort

  # 2. Step Reference (catalog step blueprint)
  - step_id: run-coverage
    override_timeout_seconds: 180
```

### Workflow Configuration Sections

| Key | Description |
| --- | --- |
| `trigger` | Command executed to test success/failure (`command`, `args`, `timeout_seconds`). |
| `agent` | LLM agent loop configuration (`provider`, `mode`, `timeout_seconds`). Providers: `gemini`, `openai`, `anthropic`, `copilot`, `cursor`, `ollama`, `local`. |
| `iteration` | Stopping criteria (`max_attempts`, `stop_when`: `trigger_passes` \| `unfixable` \| `user_abort`). |
| `sandbox` | Cleanup policy (`auto_clean`, `keep_on_failure`). |
| `approval` | Require confirmation gate (`require_before_apply`). |
| `context` | Context attached to prompt (`trigger_output`, `changed_files`, `relevant_source`). |
| `steps` | List of pipeline steps (hybrid: inline step definitions or `step_id` catalog references). |
