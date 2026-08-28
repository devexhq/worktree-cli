# Worktree CLI (`wt`) Documentation

Welcome to **Worktree CLI** (`wt`), a CLI tool providing isolated Git worktree developer workflows and AI agent workspaces backed by a local `.worktree/` state directory.

---

## Overview

`wt` streamlines developer and AI workflows by creating isolated Git worktrees and managing automated task execution cycles.

Key capabilities include:

- **Isolated Sandboxes**: Safely iterate on feature code without dirtying your main working tree using `wt sandbox`.
- **Unified Blueprint Execution**: Execute cataloged task and workflow blueprints via `wt run`.
- **Durable Resumption**: Seamlessly resume paused sessions from saved checkpoints via `wt resume`.
- **Execution History**: Inspect and audit recorded blueprint run sessions via `wt history`.
- **Catalog System**: Discover and manage project task and workflow blueprints with `wt catalog`.

---

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

---

## Documentation Map

### 🚀 Getting Started
- **[Installation](getting-started/installation.md)**: Install options via `pip`, `pipx`, `uv`, or system installer.
- **[Quickstart Tutorial](getting-started/quickstart.md)**: 5-minute tutorial to run your first blueprint in a sandbox.
- **[Workspace Configuration](getting-started/workspace-config.md)**: Set up `.worktree/config.json`, project settings, and API keys.

### 📖 How-To Guides
- **[Core Concepts](guides/concepts.md)**: Sandboxes, blueprints, tasks, workflows, and session lifecycle.
- **[Authoring Blueprints](guides/authoring-blueprints.md)**: Creating custom task and workflow documents.
- **[Working with Steps](guides/working-with-steps.md)**: Command, Agent, and Script steps, shorthands, and reusable catalog steps.
- **[Parameter Inputs & Expressions](guides/passing-inputs.md)**: Declaring typed parameters, CLI flags, and `${{ inputs.* }}` interpolation.
- **[Failure Handling & Resumption](guides/failure-handling-and-resume.md)**: Retry policies, interactive prompts, checkpoints, and `wt resume`.
- **[AI Agent Providers](guides/agent-providers.md)**: Configuring Gemini, OpenAI, Claude, Cursor, Copilot, and Ollama.

### 📚 Reference
- **[Blueprint Schema](reference/blueprint-schema.md)**: Full Task and Workflow YAML schema reference.
- **[Step Schema](reference/step-schema.md)**: Step primitive properties, modes, and loop blocks.
- **[Inputs Schema](reference/inputs-schema.md)**: Parameter input types, aliases, and expression syntax.
- **[Assertions Schema](reference/assertions-schema.md)**: Quality assertions and verification operators.
- **[Project Config Schema](reference/config-schema.md)**: Full `.worktree/config.json` specification.

### 🍳 Recipes & Examples
- **[TDD Loop](recipes/tdd-loop.md)**: Automated test-driven bug fixes.
- **[AI Code Patcher](recipes/ai-code-patcher.md)**: Multi-agent planner, patcher, and reviewer pipeline.
- **[CI/CD Automation](recipes/ci-cd-automation.md)**: Running headless Worktree blueprints in GitHub Actions.

### 💻 CLI Reference
- **[Workspace Init (`wt init`)](cli/init.md)**: Provision local workspace and configuration defaults.
- **[Status (`wt status`)](cli/status.md)**: Inspect active sandboxes, workflow sessions, and database state.
- **[Config (`wt config`)](cli/config.md)**: Display, modify, and validate project configuration.
- **[Run (`wt run`)](cli/run.md)**: Execute task and workflow blueprints.
- **[Resume (`wt resume`)](cli/resume.md)**: Resume paused blueprint sessions from checkpoint.
- **[History (`wt history`)](cli/history.md)**: List and inspect recorded blueprint runs.
- **[Sandbox (`wt sandbox`)](cli/sandbox.md)**: Git worktree isolation.
- **[Catalog (`wt catalog`)](cli/catalog.md)**: Blueprint templates and catalog items.
