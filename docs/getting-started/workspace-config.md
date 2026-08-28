# Workspace Configuration

Worktree (`wt`) operates with a local `.worktree/` directory in your Git repository root. This directory contains the configuration file (`config.json`), the SQLite state database (`data.db`), and the blueprint catalog (`catalog/`).

---

## Workspace Setup (`wt init`)

Run `wt init` at the root of your Git repository:

```bash
wt init
```

This provisions the local `.worktree/` directory structure:

```text
.worktree/
├── config.json         # Workspace configuration settings
├── data.db             # SQLite state database (runs, history, sessions)
└── catalog/            # Project blueprint definitions
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

---

## Workspace Status (`wt status`)

Inspect the current workspace status, database health, tracked sandboxes, and active sessions:

```bash
wt status
```

Output includes:
* Project configuration validation status.
* Database path and session record counts.
* Active and historical Git worktree sandboxes (`wt/` branches).

---

## Managing Configuration (`wt config`)

Inspect and modify your Worktree configuration directly using the `wt config` subcommands.

### Show Effective Configuration

Display normalized effective configuration as formatted JSON:

```bash
wt config show
```

### Update Configuration Values

Set specific configuration keys or nested dot-paths:

```bash
wt config set agent.provider ollama
wt config set agent.model llama3.1
wt config set sandbox.base_ref main
```

### Validate Configuration

Validate `.worktree/config.json` against the schema and semantic rules:

```bash
wt config validate
```

---

## Configuration Overview

Below is the canonical `.worktree/config.json` structure:

```json
{
  "version": 1,
  "project": {
    "name": "my-project",
    "initialized_at": "2026-08-06T00:00:00Z"
  },
  "paths": {
    "root_dir": ".worktree",
    "sessions_dir": ".worktree/sessions",
    "artifacts_dir": ".worktree/artifacts",
    "db_path": ".worktree/data.db"
  },
  "sandbox": {
    "base_ref": "HEAD",
    "max_active_sandboxes": 3,
    "default_timeout_seconds": 900
  },
  "agent": {
    "provider": "gemini",
    "model": "gemini-2.5-pro",
    "endpoint": null,
    "temperature": 0.2,
    "max_tokens": 4096
  },
  "history": {
    "save_attempt_logs": true,
    "save_agent_payloads": true,
    "save_final_diff": true,
    "max_sessions": 1000
  },
  "doctor": {
    "check_git": true,
    "check_paths_writable": true,
    "check_config_schema": true,
    "check_stale_worktrees": true,
    "check_required_binaries": true
  },
  "prune": {
    "remove_stale_worktrees": true,
    "remove_orphaned_sandboxes": true,
    "remove_expired_artifacts": false,
    "artifact_ttl_days": 30
  },
  "telemetry": {
    "enabled": false
  }
}
```

For full details on each field and validation rule, see the [Project Config Schema Reference](../reference/config-schema.md).

---

## API Keys & Environment Setup

Worktree supports multiple LLM agent providers: `gemini`, `openai`, `anthropic`, `cursor`, `copilot`, `ollama`, and `local`. Environment variables supply provider credentials:

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

For detailed configuration of each provider, see the [AI Agent Providers Guide](../guides/agent-providers.md).
