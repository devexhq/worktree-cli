# `wt init`

The `wt init` command initializes a project repository for Worktree (`wt`), provisioning the `.worktree/` directory structure, canonical configuration defaults, state database, and blueprint catalog folders.

## Usage

```bash
wt init [OPTIONS]
```

## Description

Running `wt init` at the root of a Git repository creates:
- `.worktree/config.json`: Project settings and execution bounds.
- `.worktree/data.db`: SQLite database for tracking sandboxes, workflow sessions, and task run logs.
- `.worktree/catalog/`: Directory structure for custom task, workflow, and step blueprints (`workflows/`, `tasks/`, `steps/`).

## Options

### `--repair`

Non-destructively repairs an existing configuration file. It scans `.worktree/config.json` and inserts any missing schema keys using default V1 canonical values, preserving your existing user configurations and initialization timestamps.

```bash
wt init --repair
```

### `--overwrite`

Destructively overwrites an existing `.worktree/config.json` file with fresh canonical V1 defaults.

```bash
wt init --overwrite
```

## Examples

### Initializing a new repository

```bash
cd /path/to/my-repo
wt init
```

Output:

```text
Initialized Worktree workspace in /path/to/my-repo/.worktree
```

### Repairing schema drift after updating `wt`

```bash
wt init --repair
```
