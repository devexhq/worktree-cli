# `wt resume`

The `wt resume` command continues a paused blueprint execution session (task or workflow), either by specifying an explicit session ID or by automatically resuming the latest paused run.

## Usage

```bash
wt resume [session_id] [OPTIONS]
```

### Arguments

| Argument | Description |
| --- | --- |
| `session_id` | Optional session identifier to resume. If omitted, the latest paused session is automatically resumed. |

### Options

| Flag | Description |
| --- | --- |
| `--non-interactive` | Disable interactive prompts; prompt_user failures abort the run instead of prompting. |

### Behavior

1. **Session Resolution**:
   - If `session_id` is provided, resumes that specific session.
   - If `session_id` is omitted, queries `RunsRepository.get_latest_paused()` and picks up the most recent paused run. If no paused session is found, renders a formatted error panel and exits with code `1`.

2. **Readiness Classification**: Validates that the session exists, is in `paused` status, and has an intact checkpoint and accessible sandbox (if sandboxed).
3. **Execution**: Re-enters step execution via `Engine.resume`.
4. **Exit Codes**:
   - `0`: Successful completion or paused run (checkpoint updated).
   - `1`: Resume validation error, failed step, cancelled run, or no paused session found.

## Examples

Auto-resume the latest paused run:

```bash
wt resume
```

Resume a specific session by ID:

```bash
wt resume task_a1b2c3d4
```

Resume non-interactively (e.g. in automated scripts):

```bash
wt resume --non-interactive
```
