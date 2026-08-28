# Working with Steps

Steps are the fundamental building blocks of Worktree blueprints. A step executes an isolated operation—such as invoking a shell command, prompting an AI agent to edit files, or executing a custom script.

---

## Step Execution Modes

Worktree supports three primary ways to define a step:

```text
Step Definition
 ├── 1. Inline Shorthand (run: <cmd>)
 ├── 2. Reusable Catalog Step (uses: <step-name>)
 └── 3. Explicit Inline Step (type: command | agent | script)
```

---

### 1. Inline Shorthand (`run:`)

For simple shell commands, use the concise `run:` key:

```yaml
steps:
  - id: install-deps
    name: Install Python dependencies
    run: uv sync --all-extras

  - id: lint-code
    name: Check code formatting
    run: ruff check .
```

*When `run:` is provided, Worktree automatically maps it to a command step.*

---

### 2. Reusable Catalog Steps (`uses:`)

Steps can be authored as standalone, reusable YAML files in `.worktree/catalog/steps/` and referenced by other blueprints via `uses:`.

```yaml
steps:
  # Reference a built-in curated step
  - id: sync-git
    uses: wt/git-sync-base

  # Reference a project-local catalog step
  - id: verify-build
    uses: build-and-test
```

#### Curated Built-in Steps (`wt/*`)
Worktree ships with curated step templates under `wt/`:
* `wt/git-sync-base`: Syncs the worktree branch with the base branch.
* `wt/ai-planner`: Prompts an AI agent to analyze an issue and produce an implementation plan.
* `wt/ai-code-patcher`: Directs an AI agent to implement changes and apply code patches in the sandbox.
* `wt/run-tests`: Runs the test suite and captures assertion outputs.
* `wt/ai-reviewer`: Prompts an AI reviewer to evaluate changes against requirements.

---

### 3. Explicit Inline Steps (`type:`)

For advanced step configuration (such as AI agent interactions or custom scripts), use explicit `type:` primitives:

#### A. Command Step (`type: command`)
Executes a shell command with custom timeouts and environment variables:

```yaml
- id: compile-assets
  name: Build Frontend
  type: command
  command: npm run build
  env:
    NODE_ENV: production
  timeout_seconds: 180
```

#### B. Agent Step (`type: agent`)
Directs an AI agent to inspect, modify, or generate code within the isolated sandbox:

```yaml
- id: fix-bug
  name: AI Bug Fixer
  type: agent
  prompt: "Refactor the authentication middleware in src/auth.py to fix issue #${{ inputs.issue_id }}"
  tools:
    - file_reader
    - file_writer
    - bash
  timeout_seconds: 300
```

#### C. Script Step (`type: script`)
Runs an executable script located within your repository:

```yaml
- id: run-validation-script
  name: Custom Validator
  type: script
  script_path: scripts/validate_schema.py
  timeout_seconds: 60
```

---

## Step Attributes Reference

Every step can be configured with the following properties:

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | `string` | Auto-generated | Unique identifier for the step (used in logs and checkpoint tracking). |
| `name` | `string` | `null` | Human-readable title displayed in the execution progress table. |
| `description`| `string` | `null` | Optional description of what the step does. |
| `timeout_seconds` | `integer` | `120` | Maximum duration before the step is terminated. |
| `env` | `map[string, string]` | `{}` | Environment variables specific to this step (supports `${{ inputs.* }}`). |
| `assert` | `StepAssert` | `null` | Declarative quality assertions (exit code, output matchers, file checks). |
| `on_failure` | `string \| FailureSpec` | `abort` | Failure policy (`abort`, `continue`, `retry`, `prompt_user`). |

---

## Loop Step Blocks (Workflows Only)

Workflows support iterative loops using `type: loop`. Loops repeat a series of nested steps until a condition is met or `max_iterations` is reached:

```yaml
steps:
  - id: tdd-loop
    name: Iterate until tests pass
    type: loop
    max_iterations: 5
    until:
      - step_pytest_verify.ok
    on_max_iterations: prompt_user
    do:
      - id: ai-code-patcher
        uses: wt/ai-code-patcher

      - id: step_pytest_verify
        name: Verify test suite
        run: pytest tests/
        assert:
          exit_code: 0
```

---

## Runtime Execution Metadata & Environment Variables

Worktree automatically exposes structured runtime metadata to step commands and templates through process environment variables (`WT_*`) and template interpolation (`{{ ... }}` or `${{ ... }}`).

### Environment Variables

Every step execution receives the complete set of `WT_*` environment variables. Values are always strings (empty string when not applicable):

| Environment Variable | Source | Description |
|---|---|---|
| `WT_STEP_ID` | `step.id` | Unique ID of the current step. |
| `WT_STEP_NAME` | `step.name` | Display name of the current step (empty if unset). |
| `WT_STEP_INDEX` | `step.index` | 1-based index of this step in the run sequence. |
| `WT_STEP_ATTEMPT` | `step.attempt` | 1-based attempt counter (increments on retries and prompt resume). |
| `WT_TASK_NAME` | `task.name` | Name of parent task blueprint (empty if unset or not a task). |
| `WT_TASK_SHA` | `task.sha` | Task run session ID (empty if unknown). |
| `WT_WORKFLOW_NAME` | `workflow.name` | Name of parent workflow blueprint (empty if unset or not a workflow). |
| `WT_WORKFLOW_SHA` | `workflow.sha` | Workflow run session ID (empty if unknown). |
| `WT_PREVIOUS_STEP_ID` | `previous_step.id` | ID of the immediately prior completed step (empty on first step). |
| `WT_PREVIOUS_STEP_NAME` | `previous_step.name` | Name of the immediately prior completed step (empty if unset). |
| `WT_PREVIOUS_STEP_INDEX` | `previous_step.index` | 1-based index of the previous step (empty on first step). |
| `WT_PREVIOUS_STEP_STATUS` | `previous_step.status` | Recorded status of previous step (`completed`, `failed`, `ignored`). |
| `WT_PREVIOUS_STEP_EXIT_CODE` | `previous_step.exit_code` | Decimal exit code of previous step (`0`, `1`, etc.; empty on first step). |

### Environment Precedence

When resolving environment variables for step execution:
1. **Explicit step `env`**: Key-value pairs declared under `env:` in the step definition take highest precedence.
2. **`WT_*` runtime metadata**: Automatically injected metadata variables.
3. **Ambient process environment**: Process environment variables from the host runner.

### Interpolation Paths

Step fields (`run`, `command`, `prompt`, `script_path`, and `env`) can reference execution metadata using `{{ <namespace>.<field> }}` or `${{ <namespace>.<field> }}` syntax:

```yaml
steps:
  - id: test-with-retry
    name: Run flaky test suite
    run: |
      if [ "$WT_STEP_ATTEMPT" -eq 1 ]; then
        exit 1
      else
        echo "Passed on attempt {{ step.attempt }}"
        exit 0
      fi
    on_failure:
      action: retry
      max_retries: 2

  - id: report-status
    name: Report previous outcome
    run: echo "Previous step {{ previous_step.id }} finished with status {{ previous_step.status }}"
```

---

## Next Steps

- Learn how to pass arguments in [Parameter Inputs & Expressions](passing-inputs.md).
- Configure assertions and retry policies in [Failure Handling & Resumption](failure-handling-and-resume.md).
- Read the [Step Schema Reference](../reference/step-schema.md) for full syntax specifications.

