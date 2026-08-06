# `wt config`

The `wt config` command inspects, updates, and validates the local `.worktree/config.json` configuration file.

## Subcommands

### `wt config show`

Displays the effective configuration loaded from `.worktree/config.json` formatted as JSON:

```bash
wt config show
```

### `wt config set`

Sets a configuration value using a dot-path key selector:

```bash
wt config set <key> <value>
```

#### Arguments

- `key`: Key or nested dot-path (e.g. `agent.provider`, `agent.model`, `sandbox.default_branch_prefix`).
- `value`: New value to store.

#### Examples

```bash
# Change LLM provider to Ollama
wt config set agent.provider ollama

# Set model name
wt config set agent.model llama3.1

# Configure custom branch prefix
wt config set sandbox.default_branch_prefix "agent/"
```

### `wt config validate`

Validates `.worktree/config.json` against the Worktree V1 JSON Schema and semantic rules:

```bash
wt config validate
```

If validation fails, `wt config validate` prints detailed error descriptions highlighting missing required fields or invalid property types.
