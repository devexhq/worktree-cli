# Blueprint Schema Reference

This reference documents the complete YAML schema for Task and Workflow blueprint definitions in Worktree.

---

## Root Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | `string` | **Yes** | — | Unique display name of the blueprint (must be at least 1 character). |
| `description` | `string` | No | `""` | Detailed description of the blueprint's goal and behavior. |
| `summary` | `string` | No | `""` | Short single-line description shown in `wt catalog list` output. |
| `id` | `string` | No | Matches `name` | Blueprint identifier. |
| `version` | `integer \| string` | No | `1` | Blueprint schema format version. |
| `use_sandbox` | `boolean` | No | `true` | When `true`, execution runs in an isolated Git worktree branch (`wt/*`). |
| `timeout_seconds`| `integer` | No | `null` | Maximum duration (in seconds, $\ge 1$) for the entire blueprint execution. |
| `env` | `map[string, string]` | No | `{}` | Key-value pairs injected as environment variables into all child steps. |
| `inputs` | `map[string, ParameterInput]` | No | `{}` | Parameter inputs accepted by the blueprint. See [Inputs Schema](inputs-schema.md). |
| `defaults` | `BlueprintDefaults` | No | `{}` | Shared defaults inherited by child steps. |
| `steps` | `list[Step \| Loop]` | No | `[]` | Ordered list of steps to execute. See [Step Schema](step-schema.md). |

---

## `defaults` Object

The `defaults` object defines blueprint-level fallback directives inherited by any child step that omits its own configuration:

| Field | Type | Default | Description |
|---|---|---|---|
| `on_failure` | `string \| FailureSpec` | `null` | Default failure handling policy copied to steps that do not define an explicit `on_failure`. |

---

## Blueprint Kinds & Restrictions

* **Task (`kind: task`)**: Stored in `.worktree/catalog/tasks/`. Tasks are strict linear sequences of standard steps. A task blueprint cannot contain `LoopStepBlock` entries.
* **Workflow (`kind: workflow`)**: Stored in `.worktree/catalog/workflows/`. Workflows support both standard steps and loop step blocks (`type: loop`).

---

## Full Example Specification

```yaml
name: full-verification-flow
description: End-to-end code generation, testing, and validation workflow
summary: Verify codebase and run full regression suite
version: 1
use_sandbox: true
timeout_seconds: 600

env:
  NODE_ENV: test
  CI: "true"

inputs:
  suite:
    type: string
    description: Target test suite name
    default: unit
    aliases: ["-s", "--suite"]

defaults:
  on_failure:
    action: retry
    max_retries: 2
    backoff_ms: 1000
    on_max_retries: prompt_user

steps:
  - id: setup
    name: Install dependencies
    run: uv sync --all-extras

  - id: run-suite
    name: Run specified test suite
    run: pytest tests/${{ inputs.suite }}
    assert:
      exit_code: 0
```
