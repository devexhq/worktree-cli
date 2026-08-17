# Worktree CLI (`wt`) Documentation

Welcome to **Worktree CLI** (`wt`), a CLI tool providing isolated Git worktree developer workflows and AI agent workspaces backed by a local `.worktree/` state directory.

## Overview

`wt` streamlines developer and AI workflows by creating isolated Git worktrees and managing automated task execution cycles.

Key capabilities include:

- **Isolated Sandboxes**: Safely iterate on feature code without dirtying your main working tree using `wt sandbox`.
- **Automated Workflows**: Define and execute bounded agent workflow loops (Plan → Execute → Verify) via `wt workflow`.
- **Reusable Tasks**: Trigger cataloged task blueprints via `wt task`.
- **Catalog System**: Discover and manage project task and workflow blueprints with `wt catalog`.

## Quickstart

Get started in seconds:

```bash
# Install Worktree CLI
pip install worktree-cli

# Initialize local worktree configuration
wt init

# List available catalog items
wt catalog list

# Create an isolated sandbox environment
wt sandbox create my-feature
```

## Documentation Map

- **[Getting Started](getting-started/installation.md)**
  - [Installation](getting-started/installation.md): Install options via `pip`, `pipx`, `uv`, or system installer.
  - [Configuration](getting-started/configuration.md): Set up `.worktree/config.json`, project settings, and API keys.
- **[CLI Reference](cli/init.md)**
  - [Workspace Init (`wt init`)](cli/init.md): Provision local workspace and configuration defaults.
  - [Status (`wt status`)](cli/status.md): Inspect active sandboxes, workflow sessions, and database state.
  - [Config (`wt config`)](cli/config.md): Display, modify, and validate project configuration.
  - [Workflow (`wt workflow`)](cli/workflow.md): Plan, execute, and verify agent loops.
  - [Task (`wt task`)](cli/task.md): Single-shot bounded actions.
  - [Sandbox (`wt sandbox`)](cli/sandbox.md): Git worktree isolation.
  - [Catalog (`wt catalog`)](cli/catalog.md): Blueprint templates and catalog items.
