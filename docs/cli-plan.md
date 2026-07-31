# Worktree CLI — Final V1 Plan

## 1) Simple Command List (V1)

```bash
wt init
wt status
wt doctor
wt prune

wt config show
wt config set <key> <value>
wt config unset <key>
wt config validate

wt loop list
wt loop show <name>
wt loop run <name>      # alias: wt loop <name>

wt history
wt history show <session-id>
wt diff <session-id>
```

---

## 2) Command Breakdown

## `wt init`

**Purpose**

Initialize Worktree in an existing Git repository.

**Inputs**
- Current working directory (must be in a Git repo)
- Optional flags (future-safe; keep minimal in v1)

**Outputs**
- Creates `.worktree/` structure
- Creates default `.worktree/config.json`
- Creates `.worktree/loops/` with starter loops
- Initializes local audit/session storage
- Prints next-step guidance

**Configuration needs**
- None required before running

**Must also handle / gotchas**
- Must fail cleanly if not in a Git repository
- Must be idempotent (running twice should not destroy user config)
- Must avoid overwriting existing user loop files
- Must handle partial initialization recovery

---

## `wt status`

**Purpose**

Show current Worktree + Git state for trust and visibility.

**Inputs**
- Current repo + `.worktree` state

**Outputs**
- Active branch + dirty/clean working tree state
- Worktree initialization status
- Active/stale sandbox count
- High-level config summary (max attempts, cleanup mode)
- Warning banners for risky states

**Configuration needs**
- Reads `.worktree/config.json` if present

**Must also handle / gotchas**
- Should still provide useful output if not initialized
- Must degrade gracefully if config is invalid/corrupt
- Must flag if stale sandboxes exist

---

## `wt doctor`

**Purpose**

Validate local environment and provide actionable fixes.

**Inputs**
- Repo state
- Local binaries/dependencies
- Config + filesystem permissions

**Outputs**
- Pass/fail checks with clear remediation hints
- Non-zero exit on critical failures
- Summary table of diagnostics

**Configuration needs**
- Reads config if present; validates schema

**Must also handle / gotchas**
- Missing Git
- Not in a repo
- Invalid config
- Unwritable `.worktree` paths
- Stale/orphaned worktree references

---

## `wt prune`

**Purpose**

Clean up stale worktree artifacts safely.

**Inputs**
- Existing sandboxes + session metadata

**Outputs**
- Removes stale sandbox directories
- Removes orphaned worktree refs
- Prints cleanup summary counts

**Configuration needs**
- `sandbox.auto_clean`
- retention settings (if added in v1; optional)

**Must also handle / gotchas**
- Must never delete active/in-use sandbox
- Must handle interrupted prior runs
- Must be safe to run repeatedly

---

## `wt config show`

**Purpose**

Display effective Worktree configuration.

**Inputs**
- `.worktree/config.json`

**Outputs**
- Full effective config (or scoped key in future)
- Source path and validation status

**Configuration needs**
- N/A

**Must also handle / gotchas**
- Missing config (show helpful guidance)
- Invalid config (surface parse + schema errors)

---

## `wt config set <key> <value>`

**Purpose**

Set a config value via CLI.

**Inputs**
- Dot-path key (`loop.default_max_attempts`)
- Value (string/number/bool)

**Outputs**
- Updated config file
- Confirmation with normalized value

**Configuration needs**
- Existing config file (or bootstrap if safe)

**Must also handle / gotchas**
- Type coercion rules must be consistent
- Reject unknown keys (strict mode for v1)
- Must preserve formatting/order predictably
- Concurrency-safe writes (atomic write)

---

## `wt config unset <key>`

**Purpose**

Remove a config key and revert to defaults.

**Inputs**
- Dot-path key

**Outputs**
- Updated config file
- Confirmation of fallback/default behavior

**Configuration needs**
- Existing config

**Must also handle / gotchas**
- Unsetting required keys should fallback, not corrupt config
- Clear message when key does not exist

---

## `wt config validate`

**Purpose**

Validate config schema and constraints.

**Inputs**
- Config file

**Outputs**
- Validation result + detailed errors/warnings
- Non-zero exit on invalid config

**Configuration needs**
- Config schema implementation

**Must also handle / gotchas**
- Structural validation + semantic validation:
- e.g., `max_attempts > 0`
- known agent provider values
- valid paths

---

## `wt loop list`

**Purpose**

List loop definitions available in `.worktree/loops`.

**Inputs**
- Loop directory contents

**Outputs**
- Table: `name`, `description`, `source file`

**Configuration needs**
- `paths.loops_dir` (default `.worktree/loops`)

**Must also handle / gotchas**
- Empty loop directory
- Invalid YAML files (show as invalid, don’t crash)

---

## `wt loop show <name>`

**Purpose**

Inspect a single loop definition before execution.

**Inputs**
- Loop name

**Outputs**
- Rendered loop config:
- trigger command
- iteration policy
- stop conditions
- sandbox settings

**Configuration needs**
- Loop schema parser

**Must also handle / gotchas**
- Name collisions / duplicate definitions
- Missing loop
- Invalid loop schema

---

## `wt loop run <name>` (alias `wt loop <name>`)

**Purpose**

Run an **iterative** agent loop in an isolated worktree.

**Inputs**
- Loop definition
- Optional flags (`--max-attempts`, `--keep`, `--approve-each`)

**Outputs**
- Attempt-by-attempt execution log
- Final status (`PASSED`, `FAILED`, `UNFIXABLE`, `ABORTED`)
- Session id
- Final diff/artifacts path
- Optional apply instructions

**Configuration needs**
- Agent provider/model defaults
- Loop attempt limits
- Sandbox cleanup behavior
- Paths for sessions/artifacts

**Must also handle / gotchas**
- Worktree creation failure
- Agent timeout/failure
- Patch application conflicts
- No-op agent responses
- Infinite-loop prevention (`max_attempts`, repeated failure signature detection)
- Keyboard interrupt (must cleanup and persist partial session)

---

## `wt history`

**Purpose**

List past loop sessions.

**Inputs**
- Session metadata store

**Outputs**
- Table with session id, loop name, status, attempts, duration, timestamp

**Configuration needs**
- `paths.sessions_dir`

**Must also handle / gotchas**
- Missing/corrupt metadata entries
- Large history (pagination/truncation strategy)

---

## `wt history show <session-id>`

**Purpose**

Show detailed execution record for one session.

**Inputs**
- Session id

**Outputs**
- Attempt timeline
- Trigger outputs
- Agent outputs summary
- Stop reason
- Artifact paths

**Configuration needs**
- Session schema

**Must also handle / gotchas**
- Partial sessions (interrupted runs)
- Unknown session id

---

## `wt diff <session-id>`

**Purpose**

Show resulting code diff from a session.

**Inputs**
- Session id
- Associated sandbox/session artifacts

**Outputs**
- Unified diff in terminal (or path to saved diff)
- File-level summary

**Configuration needs**
- Session artifact linkage

**Must also handle / gotchas**
- Session with no changes
- Missing sandbox (if cleaned) but saved diff exists
- Large diffs (truncate with full-file export path hint)

---

## 3) Milestones (One Command per Milestone)

> Sequence is chosen to unlock user value early while keeping implementation risk manageable.
> 

### Milestone 1 — `wt init`

### Milestone 2 — `wt status`

### Milestone 3 — `wt config show`

### Milestone 4 — `wt config set`

### Milestone 5 — `wt config unset`

### Milestone 6 — `wt config validate`

### Milestone 7 — `wt loop list`

### Milestone 8 — `wt loop show`

### Milestone 9 — `wt loop run`

### Milestone 10 — `wt history`

### Milestone 11 — `wt history show`

### Milestone 12 — `wt diff`

### Milestone 13 — `wt doctor`

### Milestone 14 — `wt prune`