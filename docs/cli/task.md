# `wt task`

The `wt task` command manages bounded, single-shot execution blueprints such as linting, auditing, formatting, or automated prompt actions.

## Subcommands

### `wt task` / `wt task list` (Default)

Lists available task blueprints and recent execution history. Running `wt task` without subcommands defaults to running `wt task list`:

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
```

#### Examples

```bash
wt task run audit-tokens
wt task run format-code
```

---

## Task Blueprint YAML Schema

Task blueprints live in `.worktree/catalog/tasks/<name>.yml`.

```yaml
name: audit-tokens
description: Scan project files for hardcoded API keys and token strings

command: python
args:
  - "-m"
  - "scripts.audit_tokens"
prompt: null
tools: []
script_path: null
timeout_seconds: 60
environment:
  AUDIT_STRICT: "true"
```

### Task Definition Properties

| Property | Type | Description |
| --- | --- | --- |
| `name` | string | Unique task blueprint name (required). |
| `description` | string | Human-readable explanation of what the task performs. |
| `use_sandbox` | boolean | When `true` (default if omitted), run steps in a Git sandbox worktree. When `false`, run in-place in the workspace. CLI `--no-sandbox` forces in-place regardless. |
| `command` | string | Primary shell command to execute. |
| `args` | list[string] | Arguments passed to the command. |
| `prompt` | string | LLM prompt instruction for agent-driven tasks. |
| `tools` | list[string] | Tools available to agent task runners. |
| `script_path` | string | Relative path to a local executable script. |
| `timeout_seconds` | integer | Maximum execution duration before timing out (default: `120`). |
| `environment` | dict[string, string] | Environment variables set during task execution. |
