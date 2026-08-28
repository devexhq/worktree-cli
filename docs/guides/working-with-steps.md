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

## Next Steps

- Learn how to pass arguments in [Parameter Inputs & Expressions](passing-inputs.md).
- Configure assertions and retry policies in [Failure Handling & Resumption](failure-handling-and-resume.md).
- Read the [Step Schema Reference](../reference/step-schema.md) for full syntax specifications.
