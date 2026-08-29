# `wt diff`

The `wt diff` command views syntax-highlighted unified diffs from loop run sessions directly in the terminal without manually searching `.worktree/sessions/`.

## Usage

```bash
wt diff [session_id] [OPTIONS]
```

### Arguments

| Argument | Description |
| --- | --- |
| `session_id` | Optional session identifier (e.g. `sbx_a1b2c3d4`). If omitted, displays the latest session diff. |

### Options

| Flag | Description |
| --- | --- |
| `--raw` | Output unformatted plain text diff directly to stdout without headers, Rich panels, or ANSI codes. |

## Behavior

1. **Initialization Gate**: Verifies that `.worktree/config.json` exists and is valid. If uninitialized, displays a **Worktree Not Initialized** error panel and exits with code `1`.
2. **Session Resolution**:
   - When `session_id` is supplied: resolves `.worktree/sessions/<session_id>/diff.patch`.
   - When `session_id` is omitted: discovers the most recently modified session directory under `.worktree/sessions/`.
   - If no session exists: displays a **Session Not Found** error panel and exits with code `1`.
3. **Artifact Loading**:
   - If `diff.patch` is missing: displays a **Diff Not Found** error panel and exits with code `1`.
   - If `diff.patch` is empty (0 bytes or whitespace-only): prints `No changes recorded for session <session_id>.` and exits with code `0`.
4. **Rendering**:
   - Interactive formatted output renders a header with the session ID and artifact path, followed by syntax-highlighted diff text.
   - When `--raw` is passed, outputs the exact patch content directly to stdout for redirection or piping into `git apply` / `patch`.
5. **Exit Codes**:
   - `0`: Diff successfully displayed, or empty diff.
   - `1`: Uninitialized repository, session not found, diff artifact not found, or read failure.

## Examples

View diff for the latest session:

```bash
wt diff
```

View diff for an explicit session ID:

```bash
wt diff sbx_a1b2c3d4
```

Output raw patch text (useful for piping into `git apply` or saving to a file):

```bash
wt diff sbx_a1b2c3d4 --raw > latest_fix.patch
```
