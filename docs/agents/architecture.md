# Architecture

## Layers

```
getworktree/cli.py                 Typer entrypoint, wires flags to commands
getworktree/cli/<name>/       One package per CLI subcommand
  command.py                       Orchestration: calls core/common, handles typer.Exit
  models.py                        Pydantic outcome model(s) for the command
  renderers.py                     Rich console rendering, kept out of command.py
getworktree/core/                  Business logic, no Typer/CLI concerns
  bootstrap.py                     Creates/repairs the .worktree/ directory tree
  config/{generator,loader,mutate,models,context,serialize,validate}.py
                                   Defaults write + load/set + validate + typed models + repo context
  db/                              SQLite connection, migrations, models, and domain CRUD package
  git_sandbox.py                   Isolated `git worktree` sandbox lifecycle
  inputs/                          Shared blueprint input models + resolve/interpolate services
  step/                            Step primitive definitions, resolve, assert, single-step execute
    models.py                      StepDefinition, StepAssert, AssertionResult, FailureSpec
    runner.py                      execute_step / StepResult (runs assert after dispatch)
    assertions/                    evaluate_assertions + per-key evaluators
    services/                      load/resolve step definitions from catalog
  runtime/                         Shared multi-step engine + sandbox lifecycle (`run_steps`)
  task/                            Task domain (models, loader, runner adapter, plain-text renderers)
  catalog/                         Blueprint scanning, indexing, and packaged template seeds
  catalog/services/seeder.py       Seeds curated `wt/` templates into `.worktree/catalog/`
  catalog/templates/               Packaged default.yml scaffolds + curated workflow/task/step seeds
  workflows/                       Workflow domain (models, payloads, patches, agents)
  workflows/agents/                Agent adapter protocol + providers (owned by workflows)
  workflows/services/              patch.py, payload.py, renderer.py
getworktree/common/                Shared, dependency-light helpers
  constants.py, fs.py, utils.py, schema_validation.py, models.py, exceptions.py
getworktree/schemas/                Versioned JSON Schemas (config_v1.json, workflow_v1.json)
```

Single-step execution lives in `core/step/`; multi-step orchestration lives in
`core/runtime/`.

### Domain ownership

- **Task domain** (`core/task/`) owns task models, resolution loader, runner
  adapter, and plain-text renderers
  (`models.py`, `exceptions.py`, `services/loader.py`, `services/runner.py`,
  `services/renderer.py`).
- **Inputs domain** (`core/inputs/`) owns shared task/workflow parameter
  declarations (`ParameterInput`), CLI resolve (`resolve_inputs`), and
  `${{ inputs.* }}` interpolation used during step execution.
- **Step domain** (`core/step/`) owns the step primitive model (`StepDefinition`),
  declarative `assert` block (`StepAssert` / `AssertionResult`), loaders, and
  `execute_step`. Catalog, task, and workflow YAML steps all share this
  `StepAssert` model (field alias `assert` → `assert_`).
- **Runtime domain** (`core/runtime/`) owns the shared multi-step execution
  engine (`run_steps`), `RunContext`, `RunObserver`, and `RunOutcome`.
- **Workflow domain** (`core/workflows/`) owns workflow models, payloads, patch
  validation helpers, and agent adapters (`core/workflows/agents/`).
- **Catalog domain** (`core/catalog/`) owns blueprint scanning/indexing, database
  synchronization (`CatalogDb`), and packaged template resources
  (`core/catalog/templates/`).
- **Shared core infra** stays at `core/` top level: `config/`, `git_sandbox.py`,
  `db/`, `bootstrap.py`, `inputs/`, `step/`.

Not every command has all three files (e.g. `status` has only `command.py`) — add
`models.py`/`renderers.py` when a command's output/result grows non-trivial.

### Package boundaries (import direction)

Dependencies flow one way; do not import "up" the stack:

```
common/  ->  core/{db,catalog,inputs}/  ->  core/step/  ->  core/runtime/  ->  {core/task/, core/workflows/}  ->  cli/
```

- `common/` has no dependency on anything under `core/`.
- `core/catalog/` sits alongside `db/` as shared core infra (blueprint scan,
  index, and packaged templates).
- `core/inputs/` is shared vocabulary for task and workflow blueprints; it must
  not import from `core/step/`, `core/runtime/`, `core/task/`, or
  `core/workflows/`.
- `core/step/` (step primitive definitions and execution) must not import
  from `core/runtime/`, `core/task/`, or `core/workflows/` — shared vocabulary
  that both need (e.g. failure policies) belongs in `common/` or `core/step/`,
  not in whichever package happens to define it first. Step execution may use
  `core/inputs/` for template interpolation.
- `core/runtime/` may depend on `core/step/`, `core/db/`, and `git_sandbox.py`,
  but must not import from `core/task/`, `core/workflows/`, or `cli/`.
- `core/task/` and `core/workflows/` are sibling domain packages depending on
  `core/runtime/`, `core/step/`, `core/inputs/`, and `core/catalog/`; neither
  domain imports the other.
- `cli/<name>/` packages may depend on any `core/`/`common/` module, but
  `core/`/`common/` must never import from `cli/`.

If you find yourself importing a name from a "higher" package to reuse it in a
"lower" one, move the shared piece down to the lower package (or to
`common/`) instead of adding the import.

## Adding a new command

1. Create `getworktree/cli/<name>/{__init__.py,command.py}` (add `models.py`/
   `renderers.py` once output grows past a couple of lines).
2. Implement `<name>_command(...)` in `command.py`, following the
   [Result/Outcome pattern](code-conventions.md) for anything that can partially fail.
3. Register it in [getworktree/cli.py](../../getworktree/cli.py) with `@app.command(name="...")`.
4. Add tests under `tests/cli/<name>/` mirroring [tests/cli/init](../../tests/cli/init).

## Adding a new catalog-backed domain

When creating or refactoring a blueprint domain (e.g. `task`, `workflow`, `step`):

1. **Define typed definition model**: Create `<X>Definition` in `core/<x>/models.py`
   (mirrors `TaskDefinition` / `WorkflowDefinition`).
2. **Subclass common exceptions**: In `core/<x>/exceptions.py`, define
   `<X>LoadError(DefinitionLoadError)` and
   `<X>ValidationError(DefinitionValidationError)`.
   Do not create a new base exception hierarchy.
3. **Resolve via catalog**: In `core/<x>/services/loader.py`, implement
   `resolve_and_load_<x>(name, cwd)` as a thin call to
   `get_catalog_item(name, CatalogItemType.<X>, definition_cls=<X>Definition, cwd=cwd)`.
4. **Delegate step execution**: If the domain runs steps, build a `RunContext`
   and delegate to `run_steps(context)` in `core.runtime.engine`. Do not write
   duplicate step loops or sandbox lifecycle logic.
5. **Keep CLI thin**: `cli/<x>/command.py` orchestrates
   (`resolve` → `act` → `persist` → `render`). Put Rich formatting in
   `cli/<x>/renderers.py` and plain text failure formatters in
   `core/<x>/services/renderer.py`. Never add production test seam parameters
   (such as `execute_fn=...`); use real step fixtures in tests.

## The `.worktree/` directory

`bootstrap_worktree` ([getworktree/core/bootstrap.py](../../getworktree/core/bootstrap.py))
creates this layout inside a Git repo, analogous to `.git/`:

```
.worktree/
  .meta/bootstrap.json   status, tool_version, initialized_at
  config.json            V1 config, validated against schemas/v1/config.json
  catalog/               blueprint inventory (workflows/, tasks/, steps/) + seeded wt/ templates
  workflows/             legacy bootstrap dir (workflow blueprints live under catalog/workflows/)
  sessions/              workflow session artifacts: <session_id>/diff.patch
  artifacts/, tmp/, logs/
  data.db                 SQLite token/cost + sandbox + catalog + run metadata (getworktree/core/db/)
```

Bootstrap is idempotent and never deletes user data; it only creates missing
subdirectories and repairs metadata. Catalog blueprints are ensured/scanned via
`core/catalog` (`ensure_catalog_dirs`, `scan_and_index_catalog`); curated seeds
land under `.worktree/catalog/<type>s/wt/` from `seed_all_catalog_templates`.

### Local SQLite (`data.db`)

Single file, migrated by `init_database` in
[getworktree/core/db/](../../getworktree/core/db/__init__.py). Idempotent: repeated
calls create missing tables only.

| Table | Purpose |
|-------|---------|
| `workflow_costs` | Per-step token/cost rows for workflow sessions |
| `sandboxes` | Durable sandbox metadata (name, branch, base commit, path, status) |

`sandboxes` columns: `id` (PK), `name` (nullable), `branch_name`, `base_commit`,
`sandbox_path` (UNIQUE), `status` (`active` / `merged` / `cleaned` / `conflict`,
indexed), `created_at`, `updated_at` (raw SQLite `TIMESTAMP` strings).

Typed DB surface:

- `DbBase` base database class in [getworktree/core/db/base.py](../../getworktree/core/db/base.py) providing lazy database path resolution, lazy migration execution, `@contextmanager cursor()`, and execution shortcuts (`fetch_one`, `fetch_all`, `execute`, `execute_insert`).
- Class-based repository wrappers: `SandboxesDb`, `TasksDb`, `WorkflowsDb`, `CatalogDb`, and `CostsDb`.
- Composite facade `WorktreeDb` in [getworktree/core/db/facade.py](../../getworktree/core/db/facade.py) providing properties `.sandboxes`, `.tasks`, `.workflows`, `.catalog`, `.costs`.

`git_sandbox.py` owns create/cleanup writes via `SandboxesDb` (below). CLI commands use the corresponding class repositories.

## Sandboxes

`GitSandboxManager` ([getworktree/core/git_sandbox.py](../../getworktree/core/git_sandbox.py))
owns the V1 sandbox lifecycle used by `wt sandbox create/show/delete`.

### CLI: Sandbox command group

Command package: [getworktree/cli/sandbox/](../../getworktree/cli/sandbox/)
(`command.py`, `models.py`, `renderers.py`), registered as `sandbox_app` on
[getworktree/cli.py](../../getworktree/cli.py).

Surface: `wt sandbox create|list|show|delete`. Shared patterns:

- Initialization gate (list/show/delete): `load_config_result`; on failure red
  panel **Worktree Not Initialized**, exit `1`, no DB/state files created
- Unknown id (show/delete): red panel **Sandbox Not Found**
  (`Sandbox '<id>' not found.` + fix to run `wt sandbox list`), exit `1`
- Console output via `RichOutput` / shared Rich console
- Lifecycle mutation for delete goes through `GitSandboxManager.cleanup_sandbox`
  only (command does not write the `sandboxes` table directly)

`wt diff`, `wt accept`, `wt commit`, and `wt discard` are not part of this group.

#### `wt sandbox create`

- Flags: `--name TEXT` (optional), `--base-ref TEXT` (optional),
  `--wip/--no-wip` (default `--no-wip`)
- Body: `GitSandboxManager(cwd).create_sandbox_result(name=…, base_ref=…,
  include_wip=wip)`
- Success: green `Sandbox created: <id>` plus indented `Branch:` /
  `Path:` (`display_path` relative to cwd). Non-empty `warnings` print as dim
  bullets after the block; exit `0`
- Failure: red panel **Sandbox Create Failed** with `"\n\n".join(result.errors)`
  (fallback `Sandbox creation failed.`), exit `1`. All
  `SandboxCreateStatus` failures map here (no uncaught exceptions)
- Does not re-implement manager error copy; renders `result.errors` as-is

#### `wt sandbox list`

- Initialization gate as above
- Reconciliation (always, before filter): every `active` row whose
  `sandbox_path` is not an existing directory → `update_sandbox_status(..., CLEANED)`
- Optional `--status` (`active` / `merged` / `cleaned` / `conflict`); Typer
  rejects unknown values before the command body
- Table **Worktree Sandboxes**: columns `ID`, `Name`, `Branch`, `Status`,
  `Created` (`created_at` DESC; `Name` is dim `-` when null; `Created` is the
  raw DB timestamp string)
- Empty (filtered) set → `No sandboxes found.`, exit `0`, no table
- Only DB rows are shown (orphan on-disk sandbox dirs without a row are ignored)
- Read-only except the reconciliation status write

#### `wt sandbox show <sandbox-id>`

- Initialization gate and not-found panel as above
- Lookup via `get_sandbox`; when the row is `active` and `sandbox_path` is not
  a directory → `update_sandbox_status(..., CLEANED)` for that id only, then
  render with a trailing note:
  `Note: sandbox directory is missing; status updated to 'cleaned'.`
  (exit `0`; other statuses are shown as-is with no note)
- Detail fields in order: `ID`, `Name` (`-` when null), `Branch`, `Base Commit`,
  `Path`, `Status`, `Disk` (`present` / `missing` from `Path.exists()` at render
  time), `Created`, `Updated` (raw DB timestamp strings)
- Read-only except the single-row reconciliation write

#### `wt sandbox delete <sandbox-id> [--force]`

- Initialization gate and not-found panel as above
- Lookup via `get_sandbox` only (no stale-active reconciliation on this path)
- Already `cleaned` → `Sandbox '<id>' is already cleaned; nothing to remove.`,
  exit `0`, no prompt, no `cleanup_sandbox`
- Other statuses (`active` / `merged` / `conflict`): unless `--force`, confirm
  with default **no**:
  `Delete sandbox '<id>' (branch <branch>, path <path>)?`
  `This removes the git worktree and branch. [y/N]:`
  Decline or EOF → `Aborted.`, exit `1`, no mutation
- On confirm / `--force`: rebuild `SandboxSession` from the row
  (`session_id`, `target_branch`, `sandbox_path`, `base_commit`, `name`,
  `created_at`) and call `GitSandboxManager(cwd).cleanup_sandbox(session)`
- Success: green `Sandbox deleted: <id>`, exit `0`
- Missing on-disk directory is still success (`cleanup_sandbox` is idempotent;
  row ends `cleaned`)

### On-disk layout
- Base directory: `.worktree/sandboxes/`
- Checkout path: `.worktree/sandboxes/<session_id>/`
- Throwaway branch: `worktree/sandbox-<session_id>`
- Default `session_id`: `sbx_` + 8 lowercase hex chars

### Create
- Primary API: `create_sandbox_result` → `SandboxCreateResult` (`ok` /
  `capacity_exceeded` / `git_failed` / `git_timeout` / `not_initialized` /
  `unreadable_config` / `wip_failed`; optional `warnings` never affect `ok`)
- `create_sandbox` is a thin raise-on-error wrapper over the result API
- Optional `base_ref=` override: when provided and non-empty after strip, used
  verbatim as the git ref for `git worktree add`. `None` / whitespace-only falls
  back to current branch when it is a real branch name; otherwise
  `sandbox.base_ref` from config (default `HEAD`). `wt workflow run` continues to
  omit `base_ref` (unchanged behavior)
- After successful `git worktree add`, resolve `base_commit` via
  `git rev-parse HEAD` in the sandbox (required on `SandboxSession`). Failure
  is `git_failed` / `git_timeout` and the partial worktree is discarded
- Optional `name=` (stripped; whitespace-only → `None`) stored on the session
- Optional `include_wip=True`: after worktree create, overlay uncommitted
  tracked + untracked (non-ignored) paths from the primary checkout into the
  sandbox (`apply_wip_to_sandbox`). Default remains committed tip only.
- On successful create, best-effort `insert_sandbox(...)` with
  `cwd=self.cwd` (`status=active`). DB failures append to `warnings` only
- Refuses create when active sandbox **directories** ≥
  `sandbox.max_active_sandboxes` (default `3`) without leaving a partial
  session claim on the capacity path
- Internal git plumbing (`worktree add/remove`, `branch -D`, `status` for WIP)
  uses `GIT_SUBPROCESS_TIMEOUT_SECONDS` (120s) from
  [getworktree/common/constants.py](../../getworktree/common/constants.py).
  Expiry → `git_timeout` / `SANDBOX_GIT_TIMEOUT` (distinct from trigger/agent
  timeouts; session timeout still does not cancel in-flight trigger/agent)

### Cleanup
`cleanup_sandbox` is idempotent: `git worktree remove` (force by default),
best-effort `update_sandbox_status(..., CLEANED)` (DB errors swallowed; missing
row is fine), best-effort `git branch -D`, then `git worktree prune`. Partial
state (missing dir or branch) must not raise. Used directly by
`wt sandbox delete`; there is no automatic cleanup-policy wrapper yet.

## Patch validation

`validate_patch_text` ([getworktree/core/workflows/services/patch.py](../../getworktree/core/workflows/services/patch.py))
parses and validates a unified diff against size/count/binary/path limits. It
does **not** apply the diff (no `git apply` call in this module — callers that
need to write changes to disk do so themselves, e.g. via
`core/workflows/agents/mutation_git.py`).

### API
`validate_patch_text(unified_diff, *, max_files, max_patch_kb,
reject_binary_changes=True) -> PatchApplyResult`

### Validation order
1. empty/whitespace diff → `empty_diff`
2. UTF-8 byte size > `max_patch_kb * 1024` → `too_large`
3. parse failure → `invalid_diff`
4. distinct target files > `max_files` → `too_many_files`
5. binary markers (`Binary files … differ`, `GIT binary patch`) when
   `reject_binary_changes` → `binary_rejected`
6. absolute / `..` / sandbox escape paths → `unsafe_path`

### Statuses
`checked_ok` | `empty_diff` | `too_large` | `too_many_files` |
`binary_rejected` | `unsafe_path` | `invalid_diff` (`ok` only for `checked_ok`).

## Failure payload models

`AgentFailurePayload`, `PayloadFile`, `PayloadOmission`
([getworktree/core/workflows/services/payload.py](../../getworktree/core/workflows/services/payload.py))
are the shared Pydantic models for structured agent failure context. They are
consumed by `AgentRequest.payload` in the agent adapter contract below. There is
currently no builder that assembles a payload from a live trigger run (the
previous `build_failure_payload` helper was removed with the legacy iteration
runner); callers construct `AgentFailurePayload` directly today.

## Agent adapter

`getworktree/core/workflows/agents/` owns the provider boundary for agent fix
requests. It is used today by `core/step/runner.py`'s `AGENT` step type (`wt
task run`).

### Contract
- Protocol: `AgentAdapter.propose_fix(request: AgentRequest) -> AgentResponse`
- Factory: `get_agent_adapter(provider, *, config=None)` — **v1 supports `local`,
  `ollama`, `cursor`, `gemini`, and `copilot`**; any other provider raises
  `ValueError` (`AGENT_PROVIDER_UNSUPPORTED`)
- Request carries `mode`, `AgentFailurePayload`, `sandbox_path`,
  `timeout_seconds`, optional model/endpoint/temperature/max_tokens, and
  optional `max_files`/`max_patch_kb`/`reject_binary_changes`
- Response statuses: `proposed_patch` | `no_op` | `unfixable` | `timeout` |
  `provider_error` (`ok` only for `proposed_patch`); response also carries
  optional `mutation_baseline_ref` (set only by direct-mutation providers; no
  current caller consumes it — see below)
- Diff-returning adapters (`local`, `ollama`) must not apply patches or mutate
  the sandbox beyond the child process / HTTP client. Direct-mutation adapters
  (`cursor`, `gemini`, `copilot`) mutate the sandbox directly through the shared
  base described below

### Shared direct-mutation base (`CliDirectMutationAdapter`)
- Shared module: `getworktree/core/workflows/agents/cli_mutation.py`
- Shared DTOs: `CliMutationRunRequest`, `CliMutationOutcome`,
  `CliMutationRunFn`
- Shared prompt builder: `build_mutation_prompt(request)`
- Shared flow: preflight → baseline → run → capture diff → gate → classify
- Gate violations call `discard_since` and return `provider_error`. A caller
  that wires up direct-mutation providers is responsible for resetting the
  sandbox to `mutation_baseline_ref` on any other terminal outcome (reject,
  timeout, unfixable, no-op); no execution engine currently does this.

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
instead of returning a diff. "Local runtime" means the agent workflow and
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

## Workflow run CLI (not yet executing workflows)

`wt workflow run NAME` ([getworktree/cli/workflow/command.py](../../getworktree/cli/workflow/command.py))
loads config, resolves the workflow by name, and validates it against
`workflow_v1.json`. If all of that succeeds it does **not** execute any steps —
it prints an error panel ("Workflow Run Not Implemented") and exits `1`. Step
execution is being rebuilt incrementally on top of the Workflow Spec v1 model
(`core/workflows/models.py`); track progress in issues
[#171](https://github.com/getworktree/getworktree/issues/171),
[#172](https://github.com/getworktree/getworktree/issues/172), and
[#173](https://github.com/getworktree/getworktree/issues/173). The previous
iteration controller (trigger → agent → patch-apply loop with safety tripwires
and approval gating) was removed along with its supporting `trigger.py` and
`safety.py` modules; none of that behavior currently exists.

## Packaged resources

Schemas and catalog templates ship inside the installed package and are read via
`importlib.resources.files(...)` (see shared `CONFIG_VALIDATOR` in
`common/schema_validation.py`, `WORKFLOW_VALIDATOR` in `core/workflows/models.py`,
and `core/catalog/templates/`) rather than relative filesystem paths, so they work
correctly when installed as a wheel.
