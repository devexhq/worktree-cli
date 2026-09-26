# Quickstart Tutorial

Get up and running with Worktree (`wt`) in 5 minutes. In this tutorial, you will initialize a workspace, inspect the default blueprint catalog, create an isolated sandbox, and run your first blueprint.

---

## 1. Initialize Your Workspace

Navigate to your Git repository root and run `wt init`:

```bash
wt init
```

This provisions the `.worktree/` state directory:

```text
.worktree/
├── .gitignore          # Ignores local catalog metadata, locks, and sandboxes
├── .meta/              # Local catalog metadata
├── config.json         # Project settings
├── project.json        # Project identity
└── catalog/            # Project blueprint definitions (this repo's REPO tier)
    ├── blueprints/
    └── steps/
```

Verify your workspace health:

```bash
wt status
```

---

## 2. Discover Built-in Blueprints

Worktree comes with built-in blueprint templates. List the available catalog items:

```bash
wt blueprint list
```

You can view the contents of any catalog item or scaffold template:

```bash
wt step show wt/git-sync-base
```

---

## 3. Create a Custom Blueprint

Create a new blueprint called `lint-and-format`:

```bash
wt blueprint create --name lint-and-format
```

Open `.worktree/catalog/blueprints/lint-and-format.yml` in your editor and configure its steps:

```yaml
name: lint-and-format
description: Run code linters and formatters in an isolated environment
use_sandbox: true

steps:
  - id: check-lint
    name: Lint code
    run: ruff check .
    on_failure: abort

  - id: check-format
    name: Format check
    run: ruff format --check .
    on_failure: abort
```

---

## 4. Run the Blueprint in an Isolated Sandbox

Execute your newly created blueprint:

```bash
wt run lint-and-format
```

### What Happens Behind the Scenes:
1. `wt` creates an ephemeral Git worktree sandbox on a temporary `worktree/sandbox-*` branch.
2. Each step executes sequentially inside the isolated sandbox directory.
3. If all steps succeed, the sandbox is cleanly removed.
4. The execution result, step output, and duration are recorded for the session.

---

## 5. Inspect Execution History

Audit the execution results using `wt history`:

```bash
wt history list
```

View detailed step-by-step logs and output for your run:

```bash
wt history show <session-id>
```

---

## Next Steps

- Explore [Core Concepts](../guides/concepts.md) to learn how Worktree manages sandboxes and multi-step blueprints.
- Learn how to [Author Blueprints](../guides/authoring-blueprints.md) with typed parameter inputs and assertions.
- Review [AI Agent Providers](../guides/agent-providers.md) for the current adapter set and agent-step limitation.
