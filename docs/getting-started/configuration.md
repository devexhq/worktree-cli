# Configuration

Worktree (`wt`) relies on a local `.worktree/config.json` configuration file inside your project repository root along with an SQLite state database (`.worktree/data.db`) and blueprint catalog storage (`.worktree/catalog/`).

## Workspace Setup (`wt init`)

Run `wt init` at the root of your Git repository:

```bash
wt init
```

This provisions the local `.worktree/` directory structure:

```text
.worktree/
├── config.json
├── data.db
└── catalog/
    ├── workflows/
    ├── tasks/
    └── steps/
```

### Flags & Repair Options

* `--repair`: Non-destructively inserts missing required keys into `.worktree/config.json` while preserving your custom project settings and timestamps.
* `--overwrite`: Completely replaces `.worktree/config.json` with fresh canonical V1 defaults (destructive).

```bash
# Repair an existing config file with updated schema keys
wt init --repair

# Reset configuration to fresh defaults
wt init --overwrite
```

## Workspace Status (`wt status`)

Inspect current workspace status, database health, tracked sandboxes, and active workflow sessions:

```bash
wt status
```

Output includes:
* Project configuration validation status.
* Database path and session record counts.
* Active and historical Git worktree sandboxes (`wt/` branches).

## Managing Configuration (`wt config`)

Inspect and modify your Worktree configuration directly using the `wt config` subcommands.

### Show Effective Configuration

Display normalized effective configuration as JSON:

```bash
wt config show
```

### Update Configuration Values

Set specific configuration keys or nested dot-paths:

```bash
wt config set agent.provider ollama
wt config set agent.model llama3.1
wt config set sandbox.default_branch_prefix "feature/"
```

### Validate Configuration

Validate `.worktree/config.json` against the schema and semantic rules:

```bash
wt config validate
```

## Canonical `.worktree/config.json` Schema (V1)

Below is the complete canonical V1 configuration structure:

```json
{
  "version": 1,
  "project": {
    "name": "my-project",
    "initialized_at": "2026-08-06T00:00:00Z"
  },
  "paths": {
    "sandboxes_dir": ".worktree/sandboxes",
    "db_file": ".worktree/data.db"
  },
  "sandbox": {
    "default_branch_prefix": "wt/",
    "base_ref": "main"
  },
  "workflow": {
    "default_max_attempts": 3,
    "max_attempts_hard_limit": 10,
    "default_timeout_seconds": 300
  },
  "agent": {
    "provider": "gemini",
    "model": "gemini-2.5-pro",
    "endpoint": null,
    "temperature": 0.2,
    "max_tokens": 4096
  },
  "patch": {
    "strategy": "unified_diff",
    "max_files": 50,
    "max_patch_kb": 512
  },
  "approval": {
    "require_before_apply": false
  },
  "history": {
    "max_sessions": 100
  },
  "doctor": {
    "strict_git_checks": true
  },
  "prune": {
    "artifact_ttl_days": 30
  },
  "telemetry": {
    "enabled": false
  }
}
```

## API Keys & Provider Environment Setup

Worktree supports multiple LLM agent providers: `gemini`, `openai`, `anthropic`, `copilot`, `cursor`, `ollama`, and `local`. Environment variables supply provider credentials:

```bash
# Gemini Provider
export GEMINI_API_KEY="AIzaSy..."

# OpenAI Provider
export OPENAI_API_KEY="sk-..."

# Anthropic Provider
export ANTHROPIC_API_KEY="sk-ant-..."

# GitHub Copilot Provider
export GITHUB_TOKEN="ghp_..."

# Cursor Provider
export CURSOR_API_KEY="cur_..."

# Ollama Endpoint (Local LLM)
export OLLAMA_HOST="http://localhost:11434"
```

For persistent environment setup, save provider credentials to your local shell profile (`.bashrc` / `.zshrc`) or local `.env` file (ensure `.env` is listed in `.gitignore`).
