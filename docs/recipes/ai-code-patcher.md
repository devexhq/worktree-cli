# Recipe: AI Planner, Patcher & Reviewer

This recipe demonstrates an end-to-end multi-agent workflow that plans an architectural change, patches the codebase, verifies tests, and performs an automated code review before finalizing.

---

## The Workflow Blueprint

Create `.worktree/catalog/workflows/ai-feature-dev.yml`:

```yaml
name: ai-feature-dev
description: Autonomous feature development with planner, patcher, and reviewer
summary: Multi-agent planning, implementation, and review pipeline
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

  # 2. Plan changes
  - id: ai-planner
    name: Generate Implementation Plan
    type: agent
    prompt: "Analyze the codebase and create a step-by-step implementation plan for: ${{ inputs.issue_description }}"
    timeout_seconds: 180

  # 3. Patch code
  - id: ai-patcher
    name: Implement Code Changes
    type: agent
    prompt: "Implement the planned changes for: ${{ inputs.issue_description }}. Ensure code conforms to formatting and type checks."
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

  # 5. Final AI Code Review
  - id: ai-reviewer
    name: Automated Code Review
    type: agent
    prompt: "Review the git diff generated in this sandbox. Verify that all requirements were met, no regressions were introduced, and tests cover the new code."
    timeout_seconds: 180
```

---

## Running the Recipe

Execute the workflow with a feature description:

```bash
wt run ai-feature-dev --desc "Add support for custom HTTP timeouts in the API client"
```

If any step fails, you can interactively choose to retry, or later resume with `wt resume <session-id>`.
