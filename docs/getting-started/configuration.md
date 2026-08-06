# Configuration

Worktree relies on a local `.worktree/config.json` configuration file inside your project repository.

## Initializing Configuration

Run `wt init` at the root of your Git repository:

```bash
wt init
```

This creates the `.worktree/` directory structure:

```text
.worktree/
├── config.json
├── data.db
├── workflows/
└── tasks/
```

## `.worktree/config.json` Schema

The configuration file controls project settings, sandbox paths, agent parameters, and audit storage.

```json
{
  "version": 1,
  "project": {
    "name": "my-project"
  },
  "paths": {
    "sandboxes_dir": ".worktree/sandboxes",
    "db_file": ".worktree/data.db"
  },
  "sandbox": {
    "default_branch_prefix": "wt/"
  },
  "workflow": {
    "default_max_attempts": 3
  }
}
```

## API Keys & Environment Setup

Worktree reads provider credentials from standard environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

For persistent environment setup, add credentials to your shell profile or local `.env` file (ensure `.env` is ignored in `.gitignore`).
