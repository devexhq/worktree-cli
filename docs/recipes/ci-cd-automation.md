# Recipe: CI/CD Automation & GitHub Actions

Worktree blueprints can be executed inside Continuous Integration (CI) pipelines to standardize local developer runs and remote CI validation.

---

## Key CLI Flags for CI/CD

When executing Worktree in automated environments:
* `--no-sandbox`: Disables Git worktree branch creation and executes steps directly in the runner workspace.
* `--non-interactive`: Ensures `prompt_user` failure directives degrade safely to `abort` rather than hanging on standard input.

```bash
wt run build-and-test --no-sandbox --non-interactive
```

---

## Example: GitHub Actions Workflow

Create `.github/workflows/verify-blueprints.yml`:

```yaml
name: Verify Worktree Blueprints

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install Dependencies
        run: |
          pip install uv
          uv sync --all-extras

      - name: Initialize Worktree Workspace
        run: wt init

      - name: Validate Worktree Config
        run: wt config validate

      - name: Execute Full Verification Blueprint
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          wt run lint-and-test --no-sandbox --non-interactive
```

---

## Automated Failure Diagnostics

In CI, when a step assertion fails, Worktree prints formatted diagnostics and non-zero exit codes that integrate with CI log viewers:

```text
Step 'run-tests' failed assertions:
  [FAIL] Expected exit_code 0, got 1
  [FAIL] Output did not contain '0 errors'
```
