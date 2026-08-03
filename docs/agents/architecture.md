# Architecture

## Layers

```
getworktree/cli.py                 Typer entrypoint, wires flags to commands
getworktree/commands/<name>/       One package per CLI subcommand
  command.py                       Orchestration: calls core/common, handles typer.Exit
  models.py                        Pydantic outcome model(s) for the command
  renderers.py                     Rich console rendering, kept out of command.py
getworktree/core/                  Business logic, no Typer/CLI concerns
  bootstrap.py                     Creates/repairs the .worktree/ directory tree
  config/{generator,loader,models,context}.py
                                   Defaults write + load/validate + typed models + repo context
  db.py                            SQLite token-usage ledger (for future metering)
  git_sandbox.py                   Isolated `git worktree` sandbox lifecycle
  loops/seeder.py                  Seeds packaged starter loop YAML files
  templates/loops/*.yml            Packaged starter loop definitions
getworktree/common/                Shared, dependency-light helpers
  constants.py, fs.py, utils.py, schema_validation.py
getworktree/schemas/                Versioned JSON Schemas (config_v1.json, loop_v1.json)
```

Not every command has all three files (e.g. `status` has only `command.py`) — add
`models.py`/`renderers.py` when a command's output/result grows non-trivial.

## Adding a new command

1. Create `getworktree/commands/<name>/{__init__.py,command.py}` (add `models.py`/
   `renderers.py` once output grows past a couple of lines).
2. Implement `<name>_command(...)` in `command.py`, following the
   [Result/Outcome pattern](code-conventions.md) for anything that can partially fail.
3. Register it in [getworktree/cli.py](../../getworktree/cli.py) with `@app.command(name="...")`.
4. Add tests under `tests/commands/<name>/` mirroring [tests/commands/init](../../tests/commands/init).

## The `.worktree/` directory

`bootstrap_worktree` ([getworktree/core/bootstrap.py](../../getworktree/core/bootstrap.py))
creates this layout inside a Git repo, analogous to `.git/`:

```
.worktree/
  .meta/bootstrap.json   status, tool_version, initialized_at
  config.json            V1 config, validated against schemas/config_v1.json
  loops/                 seeded + user loop definitions (validated against loop_v1.json)
  sessions/, artifacts/, tmp/, logs/
  token_audit.db          SQLite token/cost ledger (getworktree/core/db.py)
```

Bootstrap is idempotent and never deletes user data; it only creates missing
subdirectories and repairs metadata.

## Sandboxes

`GitSandboxManager` / `sandbox_scope` ([getworktree/core/git_sandbox.py](../../getworktree/core/git_sandbox.py))
own the V1 sandbox lifecycle used by loop execution.

### On-disk layout
- Base directory: `.worktree/sandboxes/`
- Checkout path: `.worktree/sandboxes/<session_id>/`
- Throwaway branch: `worktree/sandbox-<session_id>`
- Default `session_id`: `sbx_` + 8 lowercase hex chars

### Create
- Primary API: `create_sandbox_result` → `SandboxCreateResult` (`ok` /
  `capacity_exceeded` / `git_failed` / `not_initialized` / `unreadable_config`)
- `create_sandbox` is a thin raise-on-error wrapper over the result API
- Base ref: current branch when it is a real branch name; otherwise
  `sandbox.base_ref` from config (default `HEAD`)
- Refuses create when active sandbox **directories** ≥
  `sandbox.max_active_sandboxes` (default `3`) without leaving a partial
  session claim on the capacity path

### Cleanup policy
`should_cleanup_sandbox(auto_clean, keep_on_failure, command_passed)`:

| auto_clean | keep_on_failure | command_passed | clean? |
|------------|-----------------|----------------|--------|
| false | * | * | no |
| true | false | * | yes |
| true | true | True | yes |
| true | true | False | no (retain failed run) |
| true | true | None | yes (unclassified / aborted early) |

`cleanup_sandbox` is idempotent: `git worktree remove` (force by default),
best-effort `git branch -D`, then `git worktree prune`. Partial state (missing
dir or branch) must not raise.

### Context manager
`sandbox_scope(cwd, session_id=None, *, auto_clean=None, keep_on_failure=None)`
creates one sandbox, yields `SandboxSession`, and on exit applies the policy
above. Explicit kwargs override config; callers set `session.command_passed`
before leaving the scope. Body exceptions are never swallowed.


## Trigger runner

`run_trigger` ([getworktree/core/loops/trigger.py](../../getworktree/core/loops/trigger.py))
executes a loop trigger as **argv only** (`shell=False`) with `cwd` set to the
sandbox (or any working directory the caller provides).

### Inputs
- `command` + `args` (list; empty allowed)
- `cwd` — must be an existing directory or result is `cwd_missing`
- `timeout_seconds` (≥ 1) — kills the direct child on expiry
- `env` — `None` inherits the parent env; a mapping **replaces** the child env
- `log_dir` — optional artifact directory

### Result (`TriggerRunResult`)
Statuses: `passed`, `failed`, `timeout`, `spawn_failed`, `cwd_missing`.
`ok` is true only for `passed`. Captures full stdout/stderr (UTF-8 with
replacement), `exit_code` (`None` on timeout/spawn/cwd miss), `timed_out`,
`duration_ms`, and ISO-8601 `started_at` / `finished_at`.

Never prints or calls `sys.exit`. Classified outcomes do not raise.

### Artifacts (when `log_dir` is set)
Written atomically under `log_dir`:
- `trigger_stdout.log`
- `trigger_stderr.log`
- `trigger_meta.json` — `command`, `args`, `cwd`, `exit_code`, `timed_out`,
  `status`, `duration_ms`, `started_at`, `finished_at` (`indent=2`)

Artifact I/O failures become `warnings` and do **not** reclassify a successful
process outcome.

## Failure payload builder

`build_failure_payload` ([getworktree/core/loops/payload.py](../../getworktree/core/loops/payload.py))
turns a `TriggerRunResult` plus sandbox path into a bounded
`AgentFailurePayload` for agent adapters. Pure data assembly: no network, no
agent calls, no sandbox/git mutation.

### Include tokens (`context.include`)
| Token | Effect |
|-------|--------|
| `trigger_output` | Attach truncated `stdout`/`stderr` with `*_truncated` flags |
| `changed_files` | Copy caller-supplied path list onto the payload (no git) |
| `relevant_source` | Read selected source files into `files[]` |

Identity fields always set: `command`, `args`, `trigger_status`, `exit_code`,
`timed_out`, `duration_ms`. `include=[]` yields identity only.

### Caps (defaults)
- `max_trigger_chars=80_000` per stream; truncated streams append
  `\n...[truncated, original_chars=<n>]`
- `max_files=20`, `max_file_bytes=64_000` for `relevant_source`
- Candidate paths: regex extract from trigger streams (common source suffixes)
  ∪ caller `changed_files`; normalized under sandbox; sorted; de-duped
- Skips recorded in `omissions` with reason:
  `missing` | `outside_sandbox` | `directory` | `binary` | `max_files` |
  `max_file_bytes`
- Symlink escape outside the sandbox → `outside_sandbox` (no content)

## Packaged resources

Schemas and loop templates ship inside the installed package and are read via
`importlib.resources.files(...)` (see shared `CONFIG_VALIDATOR` in
`common/schema_validation.py` and `LOOP_VALIDATOR` in `core/loops/seeder.py`)
rather than relative filesystem paths, so they work correctly when installed as a
wheel.
