# Step Schema Reference

This reference documents the YAML specification for Step definitions and Loop Step blocks in Worktree.

---

## `StepDefinition` Fields

Every standard step accepts the following fields:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | `string` | **Yes** | Auto-generated | Unique step identifier. Auto-derived from `name` (slugified) if omitted in blueprint. |
| `name` | `string` | No | `null` | Display name shown during execution progress. |
| `description` | `string` | No | `null` | Optional description of the step's operation. |
| `run` | `string` | Conditional | `null` | Shorthand shell command. Mutually exclusive with `uses` and `type`. |
| `uses` | `string` | Conditional | `null` | Reference to a reusable step ID (`wt/*` or catalog step). Mutually exclusive with `run` and `type`. |
| `type` | `string` | Conditional | `null` | Primitive type: `command`, `agent`, or `script`. Mutually exclusive with `run` and `uses`. |
| `command` | `string` | Conditional | `null` | Shell command string. Required when `type: command`. |
| `prompt` | `string` | Conditional | `null` | AI agent instruction prompt. Required when `type: agent`. |
| `script_path` | `string` | Conditional | `null` | Relative path to local script. Required when `type: script`. |
| `tools` | `list[string]` | No | `[]` | List of enabled agent tools (for `type: agent`). |
| `env` | `map[string, string]` | No | `{}` | Step-specific environment variables. Supports `${{ inputs.* }}` interpolation. |
| `timeout_seconds`| `integer` | No | `120` | Maximum execution duration (seconds, $> 0$). |
| `assert` | `StepAssert` | No | `null` | Verification criteria. See [Assertions Schema](assertions-schema.md). |
| `on_failure` | `string \| FailureSpec` | No | `abort` | Failure handling policy or detailed retry object. |

---

## Step Shape Validation Rules

Worktree strictly validates step configurations:
1. **Mode Exclusivity**: A step must specify **exactly one** of `run`, `uses`, or `type`.
2. **`run` Exclusions**: When `run` is used, it cannot be combined with `uses`, `command`, `type`, `prompt`, `script_path`, or `tools`.
3. **Type Field Requirements**:
   - `type: command` $\rightarrow$ requires `command`
   - `type: agent` $\rightarrow$ requires `prompt`
   - `type: script` $\rightarrow$ requires `script_path`

---

## `on_failure` FailureSpec Object

When configuring detailed failure handling, `on_failure` can be specified as a mapping:

| Field | Type | Default | Allowed Values / Bounds | Description |
|---|---|---|---|---|
| `action` | `string` | `abort` | `abort`, `continue`, `prompt_user`, `retry` | Initial action when a step fails. |
| `max_retries` | `integer` | `3` | $\ge 1$ | Maximum number of retry attempts (when `action: retry`). |
| `backoff_ms` | `integer` | `0` | $\ge 0$ | Milliseconds to sleep between retry attempts. |
| `on_max_retries` | `string` | `abort` | `abort`, `continue`, `prompt_user` | Terminal policy when all retry attempts are exhausted. |

---

## `LoopStepBlock` (Workflows Only)

A composite step block that repeats a list of steps in `do` until an `until` condition is met:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | `string` | **Yes** | — | Unique identifier for the loop block. |
| `type` | `string` | **Yes** | `loop` | Must be `loop`. |
| `max_iterations`| `integer` | No | `5` | Maximum number of iterations ($\ge 1$). |
| `until` | `list[string]` | **Yes** | — | Termination condition expressions (e.g. `['steps.test.exit_code == 0']`). |
| `do` | `list[StepDefinition]` | **Yes** | — | List of steps to execute sequentially on each iteration. |
| `on_max_iterations` | `string` | No | `prompt_user` | Terminal policy (`abort`, `continue`, `prompt_user`) if loop reaches `max_iterations` without terminating. |

---

## Runtime Execution Metadata & Environment Variables

Step executions receive structured runtime context through `WT_*` environment variables and template interpolation paths:

### Environment Variables

| Variable | Source Path | Description |
|---|---|---|
| `WT_STEP_ID` | `step.id` | Current step ID |
| `WT_STEP_NAME` | `step.name` | Current step display name |
| `WT_STEP_INDEX` | `step.index` | 1-based index of current step |
| `WT_STEP_ATTEMPT` | `step.attempt` | 1-based attempt count for this step execution |
| `WT_TASK_NAME` | `task.name` | Name of running task blueprint (or empty) |
| `WT_TASK_SHA` | `task.sha` | Task session / run ID (or empty) |
| `WT_WORKFLOW_NAME` | `workflow.name` | Name of running workflow blueprint (or empty) |
| `WT_WORKFLOW_SHA` | `workflow.sha` | Workflow session / run ID (or empty) |
| `WT_PREVIOUS_STEP_ID` | `previous_step.id` | Step ID of immediately prior step (or empty) |
| `WT_PREVIOUS_STEP_NAME` | `previous_step.name` | Step name of immediately prior step (or empty) |
| `WT_PREVIOUS_STEP_INDEX` | `previous_step.index` | 1-based index of immediately prior step (or empty) |
| `WT_PREVIOUS_STEP_STATUS` | `previous_step.status` | Recorded status of immediately prior step (`completed`, `failed`, `ignored`, or empty) |
| `WT_PREVIOUS_STEP_EXIT_CODE` | `previous_step.exit_code` | Decimal exit code of immediately prior step (or empty) |
| `WT_STEPS_JSON` | `steps` | JSON array of finished step objects (`[{"id": "...", "name": "...", "index": "...", "status": "...", "exit_code": "..."}]`) |

### Interpolation Paths

- **Current step**: `{{ step.id }}`, `{{ step.name }}`, `{{ step.index }}`, `{{ step.attempt }}`
- **Task / Workflow**: `{{ task.name }}`, `{{ task.sha }}`, `{{ workflow.name }}`, `{{ workflow.sha }}`
- **Previous step**: `{{ previous_step.id }}`, `{{ previous_step.name }}`, `{{ previous_step.index }}`, `{{ previous_step.status }}`, `{{ previous_step.exit_code }}`
- **Historical steps (`steps`)**:
  - `{{ steps[0].<field> }}`: 0-based indexing for finished steps in run order.
  - `{{ steps[-1].<field> }}`: Python-style negative index (`-1` is the last finished step; matches `previous_step`).
  - `{{ steps.<id>.<field> }}` / `{{ steps['<id>'].<field> }}`: Keyed access by completed step ID.
  - Valid historical fields: `id`, `name`, `index` (1-based ordinal), `status`, `exit_code`.
  - The in-flight current step is never present in `steps`. Out-of-range indices or unknown step IDs safely resolve to empty strings.

### Precedence
1. Explicit step `env` key
2. `WT_*` metadata env
3. Ambient process env

