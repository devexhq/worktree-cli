# Authoring Blueprints

Blueprints are declarative YAML files stored in your project's catalog (`.worktree/catalog/`) that specify what commands, scripts, or AI agent prompts to execute.

---

## Blueprint Anatomy

Both tasks (`.worktree/catalog/tasks/*.yml`) and workflows (`.worktree/catalog/workflows/*.yml`) share a unified top-level document structure:

```yaml
name: build-and-test
description: Build package artifacts and run the full test suite
summary: Full build & verification pipeline
version: 1
use_sandbox: true
timeout_seconds: 300

env:
  NODE_ENV: test
  CI: "true"

inputs:
  target:
    type: string
    description: Target test directory
    default: tests/
    aliases: ["-t", "--target"]

defaults:
  on_failure:
    action: retry
    max_retries: 2
    backoff_ms: 500
    on_max_retries: abort

steps:
  - id: setup-env
    name: Install dependencies
    run: uv sync --all-extras

  - id: run-tests
    name: Execute tests
    run: pytest ${{ inputs.target }}
```

---

## Tasks vs. Workflows

While tasks and workflows share the same YAML structure, they have different architectural roles:

### Task (`.worktree/catalog/tasks/`)
- Represents a **single job** composed of sequential steps (e.g., code formatting, linting, or asset compilation).
- Fast and focused.
- **Restriction**: Tasks cannot contain composite loop step blocks.

### Workflow (`.worktree/catalog/workflows/`)
- Represents an **orchestrated multi-step pipeline** (e.g., TDD loop, automated bug repair, code review).
- Can contain loop steps, interactive human-in-the-loop decisions, and multi-agent coordination.

---

## Top-Level Blueprint Fields

### 1. Identity & Metadata
* `name` *(string, required)*: Unique display name.
* `description` *(string, optional)*: In-depth explanation of the blueprint's purpose.
* `summary` *(string, optional)*: Short single-sentence summary shown in `wt catalog list`.
* `version` *(integer | string, default `1`)*: Format schema version.

### 2. Execution Controls
* `use_sandbox` *(boolean, default `true`)*: Whether to create an isolated Git worktree sandbox for execution.
* `timeout_seconds` *(integer, optional)*: Overall execution timeout for the entire blueprint.
* `env` *(map[string, string], optional)*: Global environment variables injected into all child steps.

### 3. Parameter Inputs (`inputs:`)
Declare typed parameters that can be customized at runtime via CLI flags or `-i/--input`:

```yaml
inputs:
  branch:
    type: string
    description: Target branch name
    required: true
    aliases: ["-b", "--branch"]
  retries:
    type: integer
    default: 3
```

For full details, see the [Parameter Inputs Guide](passing-inputs.md).

### 4. Blueprint Defaults (`defaults:`)
You can define blueprint-wide defaults inherited by all child steps that do not specify their own:

```yaml
defaults:
  on_failure:
    action: retry
    max_retries: 3
    backoff_ms: 1000
    on_max_retries: prompt_user
```

If a step defines its own `on_failure`, the step-specific configuration takes precedence.

---

## Creating Blueprints via CLI

You can generate blueprint template scaffolds using `wt catalog create`:

```bash
# Create a new workflow blueprint
wt catalog create workflow --name fix-issue

# Create a new task blueprint
wt catalog create task --name audit-deps
```

This generates a pre-populated template in `.worktree/catalog/<type>s/<name>.yml`.

---

## Next Steps

- Explore [Working with Steps](working-with-steps.md) to configure commands, agent prompts, and reusable catalog steps.
- Read the [Blueprint Schema Reference](../reference/blueprint-schema.md) for the complete attribute specification.
