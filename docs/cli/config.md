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

### `wt config unset`

Removes a configuration value at a dot-path key, falling back to its schema default on next load:

```bash
wt config unset <key>
```

#### Arguments

- `key`: Key or nested dot-path (e.g. `agent.model`, `telemetry.enabled`).

#### Examples

```bash
# Remove a custom model override, falling back to the schema default
wt config unset agent.model

# Remove an entire section, falling back to its section defaults
wt config unset agent
```

Removing a key that is already absent is a no-op and exits successfully without writing to disk.

### `wt config validate`

Validates `.worktree/config.json` against the Worktree V1 JSON Schema and semantic rules:

```bash
wt config validate
```

If validation fails, `wt config validate` prints detailed error descriptions highlighting missing required fields or invalid property types.
