# Recipe: Agent-Step Placeholders and Quality Gates

This recipe demonstrates a blueprint containing agent-step placeholders alongside explicit quality-gate commands. Today, an agent step selects an adapter and records a placeholder result; it does not plan, patch, review, invoke a provider, or edit files.

---

## The Blueprint

Create `.worktree/catalog/blueprints/ai-feature-dev.yml`:

```yaml
name: ai-feature-dev
description: Record agent-step placeholders and run quality gates
summary: Placeholder agent steps with explicit verification commands
version: 1
use_sandbox: true

inputs:
  issue_description:
    type: string
    description: Description of the feature or bug to implement
    required: true
    aliases: ["-d", "--desc"]

steps:
  # 1. Sync branch state
  - id: git-sync
    uses: wt/git-sync-base

  # 2. Record a planning placeholder
  - id: ai-planner
    name: Record implementation-plan placeholder
    type: agent
    prompt: "Record a planning placeholder for: ${{ inputs.issue_description }}"
    timeout_seconds: 180

  # 3. Record a patching placeholder
  - id: ai-patcher
    name: Record implementation placeholder
    type: agent
    prompt: "Record an implementation placeholder for: ${{ inputs.issue_description }}"
    timeout_seconds: 300

  # 4. Verification & Quality Gates
  - id: run-linters
    name: Check code formatting and types
    run: ruff check . && basedpyright src
    assert:
      exit_code: 0
    on_failure:
      action: retry
      max_retries: 2
      backoff_ms: 1000
      on_max_retries: prompt_user

  - id: run-tests
    name: Execute test suite
    run: pytest
    assert:
      exit_code: 0

  # 5. Record a review placeholder
  - id: ai-reviewer
    name: Record code-review placeholder
    type: agent
    prompt: "Record a code-review placeholder for: ${{ inputs.issue_description }}"
    timeout_seconds: 180
```

---

## Running the Recipe

Execute the blueprint with a feature description:

```bash
wt run ai-feature-dev --desc "Add support for custom HTTP timeouts in the API client"
```

If a command step fails, you can interactively choose to retry, or later resume with `wt resume blueprint_<id>`.
