# Project Config Schema Reference

This reference documents the complete JSON schema for `.worktree/config.json` (Version 1).

---

## Canonical V1 Configuration Structure

```json
{
  "version": 1,
  "project": {
    "name": "my-project",
    "initialized_at": "2026-08-06T00:00:00Z"
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

---

## Section Breakdown

### 1. Root
* `version` *(integer, required)*: Must be integer `1`.

### 2. `project`
* `name` *(string)*: Project identifier. Defaults to directory name or `"unnamed_project"`.
* `initialized_at` *(string \| null)*: ISO 8601 creation timestamp.

### 3. `sandbox`
* `base_ref` *(string)*: Base Git reference to branch from (default: `"HEAD"`).
* `max_active_sandboxes` *(integer)*: Maximum allowed concurrent sandboxes (default: `3`).
* `default_timeout_seconds` *(integer)*: Sandbox timeout ceiling in seconds (default: `900`).

### 4. `agent`
* `provider` *(string)*: Agent provider: `local`, `ollama`, `cursor`, `gemini`, `copilot`, `openai`, `anthropic`, `azure_openai`, `custom`.
* `model` *(string \| null)*: Target LLM model name.
* `endpoint` *(string \| null)*: Custom API endpoint URL (e.g. for Ollama).
* `temperature` *(number)*: Sampling temperature (default: `0.2`).
* `max_tokens` *(integer)*: Maximum generation tokens (default: `4096`).

### 5. `history`
* `save_attempt_logs` *(boolean)*: Record individual step attempt outputs (default: `true`).
* `save_agent_payloads` *(boolean)*: Record LLM prompts and responses (default: `true`).
* `save_final_diff` *(boolean)*: Record git diffs on session completion (default: `true`).
* `max_sessions` *(integer)*: Maximum historical sessions to retain (default: `1000`).

### 6. `doctor`
* `check_git` *(boolean)*: Verify Git binary presence and repository state (default: `true`).
* `check_paths_writable` *(boolean)*: Verify storage writability (default: `true`).
* `check_config_schema` *(boolean)*: Check configuration integrity (default: `true`).
* `check_stale_worktrees` *(boolean)*: Detect abandoned worktrees (default: `true`).
* `check_required_binaries` *(boolean)*: Verify required tool binaries (default: `true`).

### 7. `prune`
* `remove_stale_worktrees` *(boolean)*: Prune dead worktrees during cleanup (default: `true`).
* `remove_orphaned_sandboxes` *(boolean)*: Delete unindexed sandbox directories (default: `true`).
* `remove_expired_artifacts` *(boolean)*: Delete artifacts past TTL (default: `false`).
* `artifact_ttl_days` *(integer)*: Artifact retention window in days (default: `30`).

### 8. `telemetry`
* `enabled` *(boolean)*: Anonymous telemetry collection flag (default: `false`).
