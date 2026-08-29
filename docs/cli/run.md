# `wt run`

The `wt run` command executes any blueprint by name (task or workflow) from the
catalog without requiring the user to specify the blueprint kind.

## Usage

```bash
wt run <name> [OPTIONS] [-- <input-overrides>]
```

### Options

| Flag | Description |
| --- | --- |
| `--no-sandbox` | Run execution in-place in the working tree without creating a Git sandbox. |
| `--keep` | Retain the sandbox worktree after execution. |
| `--auto-apply` | Automatically apply sandbox changes to the main workspace on successful completion. |
| `--agent <name>` | Override the default target agent adapter. |
| `--session-id <id>` | Explicit session identifier. |
| `--non-interactive` | Disable interactive prompts; prompt_user failures abort the run instead of blocking for input. |

Trailing CLI arguments (after options) are forwarded to declared blueprint inputs.

### Behavior

1. **Resolution**: Resolves `<name>` from `.worktree/catalog/` via `Blueprint.load`.
2. **Kind Detection**: Automatically detects whether the resolved blueprint is a `task` or `workflow`.
3. **Execution**: Runs the blueprint through the unified runtime engine (`BlueprintRunService`).
4. **Exit Codes**:
   - `0`: Successful run or paused run (with checkpoint saved).
   - `1`: Failed or cancelled run.

## Examples

Run a task blueprint:

```bash
wt run build-task
```

Run a workflow blueprint in-place without sandbox:

```bash
wt run release-flow --no-sandbox
```

Pass declared blueprint inputs:

```bash
wt run test-suite --target src/worktree --verbose true
```

Run non-interactively in CI:

```bash
wt run lint-all --non-interactive
```
