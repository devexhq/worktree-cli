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
  agents/{base,local,factory}.py   Agent adapter protocol + local provider
  config/{generator,loader,models,context}.py
                                   Defaults write + load/validate + typed models + repo context
  db.py                            SQLite token-usage ledger (for future metering)
  git_sandbox.py                   Isolated `git worktree` sandbox lifecycle
  loops/seeder.py                  Seeds packaged starter loop YAML files
  loops/patch.py                   Unified-diff validate/apply in sandbox
  loops/runner/                    Iteration controller (package: models/helpers/steps/orchestrator)
  loops/safety.py                  Repeat-failure / no-op / session-timeout policy
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
  `capacity_exceeded` / `git_failed` / `not_initialized` / `unreadable_config` /
  `wip_failed`)
- `create_sandbox` is a thin raise-on-error wrapper over the result API
- Base ref: current branch when it is a real branch name; otherwise
  `sandbox.base_ref` from config (default `HEAD`)
- Optional `include_wip=True`: after worktree create, overlay uncommitted
  tracked + untracked (non-ignored) paths from the primary checkout into the
  sandbox (`apply_wip_to_sandbox`). Default remains committed tip only.
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
- `max_trigger_chars=20_000` per stream; truncated streams keep the **tail**
  (failure details are usually at the end) and prefix
  `...[truncated, original_chars=<n>]\n`
- `max_files=20`, `max_file_bytes=64_000` for `relevant_source`
- Candidate paths for `relevant_source`:
  1. Prefer failing test files inferred from trigger output (pytest
     `FAILED`/`ERROR` node lines, else `file.py:line` markers)
  2. If none found: regex extract from trigger streams (common source
     suffixes) ∪ caller `changed_files`
  Paths are normalized under sandbox, de-duped, then sorted
- When failing test files are identified, only those files are attached
  (a single failing test → one source file), not the full changed-file set
- Skips recorded in `omissions` with reason:
  `missing` | `outside_sandbox` | `directory` | `binary` | `max_files` |
  `max_file_bytes`
- Symlink escape outside the sandbox → `outside_sandbox` (no content)

## Patch apply engine

`apply_patch_result` ([getworktree/core/loops/patch.py](../../getworktree/core/loops/patch.py))
validates and applies agent patches to a sandbox tree. Strategy is
**`unified_diff` only**. Callers pass limits; the engine does not load config.
Never commits or stages. Classified outcomes do not raise.

### API
`apply_patch_result(*, sandbox_path, unified_diff, max_files, max_patch_kb,
reject_binary_changes=True, check_only=False) -> PatchApplyResult`

### Pre-apply validation order
1. empty/whitespace diff → `empty_diff`
2. UTF-8 byte size > `max_patch_kb * 1024` → `too_large`
3. parse failure → `invalid_diff`
4. distinct target files > `max_files` → `too_many_files`
5. binary markers (`Binary files … differ`, `GIT binary patch`) when
   `reject_binary_changes` → `binary_rejected`
6. absolute / `..` / sandbox escape paths → `unsafe_path`
7. missing sandbox directory → `sandbox_missing`

### Apply
Uses `git apply --verbose` with `cwd=sandbox_path` (no `--unsafe-paths`).
`check_only=True` adds `--check` and does not write. `git apply` reject is
atomic (working tree unchanged on failure) → status `conflict`. Success →
`applied` or `checked_ok` with sorted unique POSIX `touched_files`.

### Statuses
`applied` | `checked_ok` | `empty_diff` | `too_large` | `too_many_files` |
`binary_rejected` | `unsafe_path` | `invalid_diff` | `conflict` |
`sandbox_missing` (`ok` only for `applied` / `checked_ok`).

## Agent adapter

`getworktree/core/agents/` owns the provider boundary for loop fix requests.

### Contract
- Protocol: `AgentAdapter.propose_fix(request: AgentRequest) -> AgentResponse`
- Factory: `get_agent_adapter(provider, *, config=None)` — **v1 supports `local`,
  `ollama`, `cursor`, `gemini`, and `copilot`**; any other provider raises
  `ValueError` (`AGENT_PROVIDER_UNSUPPORTED`)
- **Loop** `agent.provider` selects the adapter; **config** `agent.model` /
  `endpoint` / `temperature` / `max_tokens` populate `AgentRequest`
- Request carries `mode`, `AgentFailurePayload`, `sandbox_path`,
  `timeout_seconds`, optional model/endpoint/temperature/max_tokens, and
  optional `max_files`/`max_patch_kb`/`reject_binary_changes`
- Response statuses: `proposed_patch` | `no_op` | `unfixable` | `timeout` |
  `provider_error` (`ok` only for `proposed_patch`); response also carries
  optional `mutation_baseline_ref` (set only by direct-mutation providers)
- Diff-returning adapters (`local`, `ollama`) must not apply patches or mutate
  the sandbox beyond the child process / HTTP client. Direct-mutation adapters
  (`cursor`, `gemini`, `copilot`) mutate the sandbox directly through the shared
  base described below

### Shared direct-mutation base (`CliDirectMutationAdapter`)
- Shared module: `getworktree/core/agents/cli_mutation.py`
- Shared DTOs: `CliMutationRunRequest`, `CliMutationOutcome`,
  `CliMutationRunFn`
- Shared prompt builder: `build_mutation_prompt(request)`
- Shared flow: preflight → baseline → run → capture diff → gate → classify
- Gate violations call `discard_since` and return `provider_error`; the runner
  later uses `mutation_baseline_ref` to reset the sandbox when needed

### Local provider (`LocalAgentAdapter`)
Resolves argv from `WORKTREE_LOCAL_AGENT_CMD` (`shlex.split`) or default
`worktree-local-agent` on `PATH`.

| Channel | Content |
|---------|---------|
| cwd | `request.sandbox_path` |
| stdin | JSON serialization of `AgentRequest` (UTF-8) |
| stdout | JSON matching `LocalAgentStdout` (`extra=forbid`) |
| timeout | wall clock `request.timeout_seconds` → status `timeout` |

Stdout mapping: `unfixable=true` → `unfixable`; non-empty `unified_diff` →
`proposed_patch`; else `no_op`. Invalid/missing JSON, spawn failures, and schema
violations → `provider_error`. Classified outcomes never raise.

### Ollama provider (`OllamaAgentAdapter`)
In-process HTTP client (stdlib `urllib`) — no `WORKTREE_LOCAL_AGENT_CMD`.

| Setting | Resolution |
|---------|------------|
| model | `request.model` (required; else `provider_error` — set `agent.model` in config) |
| endpoint | `request.endpoint` → env `OLLAMA_HOST` → `http://127.0.0.1:11434` |
| temperature | `request.temperature` or `0.2` |
| max tokens | `request.max_tokens` or `4096` → Ollama `options.num_predict` |

`POST {base}/api/chat` with `stream: false`, system+user messages, wall-clock
`request.timeout_seconds`. Endpoint must be absolute `http://` or `https://`.

Model must return JSON fields `unfixable`, `unfixable_reason`,
`unified_diff`, `summary` (fences stripped). Mapping matches local stdout rules;
**unparseable model text → `unfixable`** with reason `model_output_unparseable`
(not `provider_error`). Transport/HTTP failures → `provider_error`; wall timeout
→ `timeout`.

### Cursor provider (`CursorAgentAdapter`)
Direct-mutation provider: the Cursor SDK agent edits sandbox files on disk
instead of returning a diff. "Local runtime" means the agent loop and
filesystem access run on this machine (`LocalAgentOptions(cwd=sandbox_path)`);
the model itself is always Cursor-hosted. Auth via `CURSOR_API_KEY`; the SDK is
an optional install (`pip install getworktree[cursor]`), imported lazily.

### Gemini provider (`GeminiAgentAdapter`)
Direct-mutation provider backed by the `gemini` CLI subprocess. Auth via
`GEMINI_API_KEY`. The CLI runs in the sandbox working directory and returns JSON
output that is mapped to the same direct-mutation base flow.

### Copilot provider (`CopilotAgentAdapter`)
Direct-mutation provider backed by `gh copilot`. Auth via `GH_TOKEN` or
`GITHUB_TOKEN`. The CLI runs in the sandbox working directory and returns
JSONL output that is mapped to the same direct-mutation base flow.

The runner (`run_loop_iteration`) treats any response with
`mutation_baseline_ref is not None` as direct-mutation: on approval it skips
re-`git apply` (files are already correct) and only re-derives touched files
via `validate_patch_text`; on any other terminal outcome (reject, timeout,
unfixable, no-op) it calls `discard_since` to reset the sandbox back to
baseline before the next attempt. `local`/`ollama` never set
`mutation_baseline_ref`, so their code path is unchanged.

## Iteration controller

`run_loop_iteration` ([getworktree/core/loops/runner/runner.py](../../getworktree/core/loops/runner/runner.py))
owns one full loop **session** attempt cycle. No Rich printing; returns
`LoopRunResult` only. Engines are injected for tests (`run_trigger_fn`,
`apply_patch_fn`, `agent`, sandbox create/cleanup, etc.). The `runner` package
also has `runner_models.py` (run-result models and callback type aliases,
a sibling module), `helpers.py` (stateless utilities), and `steps.py`
(`_LoopContext` plus the per-attempt `_run_*_step` functions);
`getworktree.core.loops.runner` re-exports the full public API, so external
imports are unaffected by this internal layout.

### Attempt flowchart

```mermaid
flowchart TD
  start[Create sandbox once] --> checkAbort{Aborted?}
  checkAbort -->|yes| aborted[ABORTED / user_abort]
  checkAbort -->|no| trigger[Run trigger in sandbox]
  trigger --> passed{Trigger passed?}
  passed -->|yes| ok[PASSED / trigger_passed]
  passed -->|no| abort2{Aborted?}
  abort2 -->|yes| aborted
  abort2 -->|no| payload[Build failure payload]
  payload --> agent[Agent propose_fix]
  agent --> unfix{unfixable and in stop_when?}
  unfix -->|yes| unf[UNFIXABLE / agent_unfixable]
  unfix -->|no| soft{timeout / provider_error / no_op?}
  soft -->|yes| nextOrFail{Attempts remain?}
  soft -->|no| patchPath{proposed_patch}
  patchPath --> approve{require_before_apply?}
  approve -->|yes, reject or missing cb| nextOrFail
  approve -->|no or approved| apply[apply_patch_result]
  apply --> nextOrFail
  nextOrFail -->|yes| checkAbort
  nextOrFail -->|no| fail[FAILED / max_attempts_exhausted]
```

### Max attempts
```text
effective = caller_max_attempts or loop.iteration.max_attempts
effective = min(effective, config.loop.max_attempts_hard_limit)
```
`effective < 1` → `configuration_error` (no attempts).

### Final statuses / stop_reason
| status | stop_reason examples |
|--------|----------------------|
| `PASSED` | `trigger_passed` |
| `FAILED` | `max_attempts_exhausted`, `sandbox_create_failed`, `configuration_error` |
| `UNFIXABLE` | `agent_unfixable` |
| `ABORTED` | `user_abort` (terminal even if `user_abort` missing from `stop_when`) |

### Sandbox / approval
- One sandbox per session; `session.command_passed` is `True` only on final
  `PASSED`, `False` on FAILED/UNFIXABLE, `None` on ABORTED
- Cleanup via `should_cleanup_sandbox` using loop sandbox flags (overridable)
- When `approval.require_before_apply` is true: call `approve_patch(diff)`;
  missing callback → `configuration_error` / `approval_callback_missing`

### Hooks
- `abort_event` / `is_aborted` checked before attempt, after trigger, after
  agent, before/after patch
- `on_event(name, payload)` and `on_attempt_end(record)` for UX/history

## Safety controls

`getworktree/core/loops/safety.py` holds pure helpers + `SafetyState`; the
iteration controller evaluates them at checkpoints.

| Tripwire | Threshold | Config | `stop_reason` | Final status |
|----------|-----------|--------|---------------|--------------|
| Repeat failure signature | 3 consecutive identical failed triggers | `loop.detect_repeat_failures` (false disables **only** this) | `repeat_failure_signature` | `FAILED` |
| Agent no-op streak | 2 consecutive `no_op` | always on | `agent_no_op_streak` | `FAILED` |
| Session wall-clock | `session_timeout_seconds` (default `sandbox.default_timeout_seconds`) | always on when > 0 | `session_timeout` | `FAILED` |
| User abort | abort event / `is_aborted` | always on | `user_abort` | `ABORTED` |

### Failure signature
`failure_signature(trigger_status, exit_code, stdout, stderr)` → full sha256 hex
of `status|exit_code|stdout_tail|stderr_tail` (tails: last 4000 chars, whitespace
collapsed). Successful trigger resets the consecutive signature counter; a
different signature also resets it.

### Session timeout checkpoints
Checked before each attempt starts and before the agent call. Does not cancel an
in-flight trigger/agent; if the agent returns after the deadline, the next
checkpoint still stops with `session_timeout`.

### Abort
CLI should set the same abort flag on SIGINT and let the controller finish
cleanup (`should_cleanup_sandbox` with `command_passed=None` on abort).

## Loop run CLI UX

`wt loop run NAME` ([getworktree/commands/loop/command.py](../../getworktree/commands/loop/command.py))
orchestrates resolve → validate → `run_loop_iteration` → render. Formatting lives
in [renderers.py](../../getworktree/commands/loop/renderers.py) (no bare `print`).

### Live progress
The CLI registers `on_event` and prints plain progress as the controller emits:
`session_start`, `attempt_start`, `trigger_start` / `trigger`, `agent_start` /
`agent`, `patch_start` / `patch` (plus optional prompt-dump events when enabled).
Start events use a `running...` line so long triggers/agents do not look stalled.
After the run, only the summary is reprinted (attempt blocks are not duplicated
when progress streamed).

### Flags
- `--max-attempts INT` (≥1) → controller `caller_max_attempts`
- `--keep / --no-keep` → `--keep` forces `auto_clean=False`
- `--approve-each / --no-approve-each` → override approval gate; default follows
  loop `approval.require_before_apply` (non-TTY deny)
- `--wip / --no-wip` → overlay uncommitted working-tree changes into the sandbox
  (tracked + untracked, not ignored); default off
- `--dump-prompt / --no-dump-prompt` → dump provider-specific agent input to
  `/tmp/wt-agent-prompt-<session>-attempt-<nn>.(txt|json)` before each agent call

### Approval prompt
When the approval gate is on, the CLI prints a bordered `rich.panel.Panel`
review block (`build_patch_review_panel` in
[renderers.py](../../getworktree/commands/loop/renderers.py)) before the y/N
prompt: touched files, `+/-` line stats in the title, and the unified diff body
(truncated after 200 lines) with added lines in green, removed lines in red,
hunk headers in cyan, and file headers bold. Non-TTY stdin still prints the
panel, then denies.

### Exit codes
| Final status | Exit |
|--------------|------|
| `PASSED` | 0 |
| `FAILED` | 1 |
| `UNFIXABLE` | 2 |
| `ABORTED` | 130 |
| pre-run resolve/validate/config failure | 1 |

Summary labels: `Loop:`, `Status:`, `Session:`, `Attempts:`, `Stop:`,
`Sandbox:`, `Artifacts:`, `Next:`.

## Packaged resources

Schemas and loop templates ship inside the installed package and are read via
`importlib.resources.files(...)` (see shared `CONFIG_VALIDATOR` in
`common/schema_validation.py` and `LOOP_VALIDATOR` in `core/loops/seeder.py`)
rather than relative filesystem paths, so they work correctly when installed as a
wheel.
