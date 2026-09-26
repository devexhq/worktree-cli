# Recipe: Test-Driven Development (TDD) Loop

This recipe demonstrates a generic blueprint loop that records an agent-step placeholder and runs tests. The agent step does not write implementation code or invoke a provider.

---

## The Blueprint

Create `.worktree/catalog/blueprints/tdd-cycle.yml`:

```yaml
name: tdd-cycle
description: Iterative test-driven development cycle
summary: Record agent-step placeholders while rerunning tests
version: 1
use_sandbox: true

inputs:
  test_file:
    type: string
    description: Target test file containing failing tests
    required: true
    aliases: ["-t", "--test"]

  max_attempts:
    type: integer
    description: Maximum iterations
    default: 5
    aliases: ["-m", "--max-attempts"]

steps:
  - id: verify-initial-tests
    name: Run initial tests (expect failure)
    run: pytest ${{ inputs.test_file }}
    on_failure: continue

  - id: tdd-loop
    name: Test observation loop
    type: loop
    max_iterations: 5
    until:
      - steps.run-test-suite.exit_code == 0
    on_max_iterations: prompt_user
    do:
      - id: ai-code-patcher
        name: Record test-failure placeholder
        type: agent
        prompt: "Record a placeholder for test failures in ${{ inputs.test_file }}."
        timeout_seconds: 180

      - id: run-test-suite
        name: Run test suite
        run: pytest ${{ inputs.test_file }}
        assert:
          exit_code: 0
```

---

## Running the Recipe

1. Write a failing test in `tests/test_calculator.py`.
2. Execute the TDD blueprint:

```bash
wt run tdd-cycle --test tests/test_calculator.py
```

### Execution Flow:
1. Worktree spins up an isolated sandbox worktree.
2. The agent step selects an adapter and records a placeholder result; it does not inspect or modify the codebase.
3. The test suite runs after each attempt.
4. As soon as all assertions pass (`steps.run-test-suite.exit_code == 0`), the loop terminates with success.
