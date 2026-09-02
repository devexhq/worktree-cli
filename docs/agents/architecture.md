# Architecture

Structural map for agents. **File placement rules** (where models vs services live) are in
[code-conventions.md](code-conventions.md#core-package-layout).
User-facing command behavior lives under [docs/cli/](../cli/). Entity shapes and schemas live in [schemas.md](schemas.md).

## Layers

**Relevant sources:** `src/worktree/cli/`, `src/worktree/core/`, `src/worktree/common/`, `src/worktree/schemas/`.

```
src/worktree/cli/cli.py              Typer entrypoint
src/worktree/cli/<name>/             One package per CLI subcommand (thin wrappers over domain)
  app.py                             Typer app / command registration
  commands/                          Command handlers (e.g. root.py, commands/<action>.py)
  models.py                          CLI outcome and presentation models
  renderers.py                       Rich terminal rendering
  formatters.py                      String layout formatters

src/worktree/core/                   Business logic (no Typer)
  bootstrap/                         models.py, facade.py (Bootstrap), services/{bootstrap,initialize}.py
  git/                               models.py, runner.py (GitRunner), exceptions.py
  sandbox/                           models.py, exceptions.py, facade.py (Sandbox), services/{delete,detector,lifecycle,list,patch,pruner,show,wip}.py
  config/                            models.py, exceptions.py, facade.py (Config), generator.py, loader.py, mutate.py, parser.py, serialize.py, validate.py
  db/                                models.py, facade.py (WorktreeDb), connection.py, migrations.py, repositories/, alembic/
  inputs/                            models.py, facade.py (Inputs), services/{interpolate,renderer,resolve}.py
  catalog/                           models.py, exceptions.py, facade.py (Catalog), services/{inventory,seeder}.py, templates/
  blueprint/                         models.py, exceptions.py, facade.py (Blueprint), renderers.py
  diff/                              models.py, facade.py (Diff), renderers.py, services.py, writer.py
  status/                            models.py, facade.py (Status), services/collector.py
  history/                           models.py, facade.py (History), renderers.py, services.py
  step/                              models.py, exceptions.py, facade.py (Step), runner.py, assertions/, services/{conditions,loader,metadata,resolver}.py, utils/
  runtime/                           models.py, exceptions.py, engine.py (entrypoint: run_steps), failure.py, loop_runner.py, observer.py, prompter.py
  engine/                            models.py, exceptions.py, engine.py (entrypoint: Engine class), resumable.py, writer.py, services/{reconcile,resume,run}.py
  agents/                            models.py, exceptions.py, base.py, factory.py, cli_mutation.py, mutation_git.py, providers (local, ollama, cursor, gemini, copilot)
  patch/                             models.py, exceptions.py, patch.py

src/worktree/common/                 Shared helpers (no core/ imports)
  filesystem/                        models.py, facade.py (Filesystem), services/{git,operations,paths,yaml}.py
  constants.py, exceptions.py, formatters.py, lock.py, models.py, process.py, schema_validation.py, types.py, utils.py, version.py

src/worktree/schemas/v1/             Versioned JSON Schemas (config.json, workflow.json)
```

- Default for **new** domain code: `models.py` + `services/<verb>.py`. Do not extend the flat `config/` / `db/` pattern to new domains.
- Single-step execution: `core/step/` (`runner.py`).
- Multi-step orchestration: `core/runtime/` (`engine.py` -> `run_steps`).
- Process facade: `core/engine/` (`Engine.run` / `Engine.resume`, `BlueprintRunService` / `BlueprintResumeService`).

> **Naming hazard:** `core/runtime/engine.py` (`run_steps`) and `core/engine/engine.py` (`Engine` class) are two distinct modules sharing the filename `engine.py`. When importing, double-check which package you intend.

### Domain ownership

**Relevant sources:** `src/worktree/core/`

- **Inputs** (`core/inputs/`): `ParameterInput`, CLI flag resolution, `${{ inputs.* }}` placeholder interpolation. Must not import step, runtime, agents, or patch.
- **Step** (`core/step/`): `StepDefinition`, `StepAssert` / assertions, `StepExecution`, step-local failure recovery. Must not import runtime.
- **Agents** (`core/agents/`): Adapter protocol (`AgentAdapter`), provider implementations (`local`, `ollama`, `cursor`, `gemini`, `copilot`), failure payload models. Must not import step or runtime.
- **Patch** (`core/patch/`): Unified-diff parsing and validation. Must not import agents, step, or runtime.
- **Blueprint** (`core/blueprint/`): Unified task/workflow document handle (`Blueprint`), catalog/path loader, input declaration schema. Must not import runtime, engine, or cli.
- **Runtime** (`core/runtime/`): Step-loop execution (`run_steps`), `RunContext` / `RunObserver` / `RunOutcome`, failure orchestration (abort / continue / `prompt_user`), and pause checkpoint persistence. Runtime must not import cli.
- **Engine** (`core/engine/`): Process-level run persistence, session ID minting (`RunRequest`), DB run records, run/resume services (`BlueprintRunService`, `BlueprintResumeService`, `reconcile_stale_runs`). Must not import cli.
- **Catalog** (`core/catalog/`): Template scanning, indexing, `CatalogDb` sync hooks, packaged seeds under `templates/`.
- **History** (`core/history/`): `HistoryListService`, `HistoryShowService`, result models, and table/panel renderers.
- **Diff** (`core/diff/`): `DiffService`, session diff resolution, artifact loading, result models, and terminal renderers.
- **Status** (`core/status/`): Workspace health and runtime telemetry collection (`collect_status`), result models (`WorktreeStatusResult`), warning aggregation.
- **Sandbox** (`core/sandbox/`): Isolated git worktree checkout creation, deletion, listing, show, prune, and patch application (`Sandbox` facade, `services/lifecycle.py`).
- **Shared core infra**: `config/`, `db/`, `git/`, `bootstrap/`.

### Package boundaries (import direction)

Dependencies flow one way down the stack; do not import upward:

```
common/  ->  core/{db,git,sandbox,catalog,inputs,patch,history,diff,status}/  ->  core/agents/  ->  core/step/  ->  {core/runtime/, core/blueprint/}  ->  core/engine/  ->  cli/
```

- `common/` never depends on `core/`.
- `core/inputs/` must not import `step`, `runtime`, `agents`, or `patch`.
- `core/patch/` must not import `agents`, `step`, or `runtime`.
- `core/agents/` may use `patch/` and `config/`; must not import `step` or `runtime`.
- `core/step/` must not import `runtime`.
- `core/runtime/` may use `step/`, `db/`, `sandbox/`; must not import `blueprint/`, `engine/`, or `cli/`.
- `core/blueprint/` may use `catalog/`, `inputs/`, `step/`; must not import `runtime/`, `engine/`, or `cli/`.
- `core/engine/` may use `runtime/`, `blueprint/`, `db/`; must not import `cli/`.
- `cli/` may import `core/` and `common/`; lower layers never import `cli/`.

## Adding a new command

**Relevant sources:** `src/worktree/cli/`, `src/worktree/cli/cli.py`

1. Create `src/worktree/cli/<name>/` with `app.py`, `commands/<action>.py` (or `commands/root.py`), `models.py`, `renderers.py`.
2. Wire command logic directly to underlying domain services or facades (e.g. `BlueprintRunService`, `HistoryListService`). Keep CLI packages free of business logic, DB queries, or direct filesystem scans.
3. Register the command in [src/worktree/cli/cli.py](../../src/worktree/cli/cli.py).
4. Add tests under `tests/cli/<name>/`.

## Adding a new catalog-backed domain

1. **Models**: `<X>Definition` in `core/<x>/models.py`.
2. **Exceptions**: `<X>LoadError` / `<X>ValidationError` subclassing definition errors in `core/<x>/exceptions.py`.
3. **Loader**: `core/<x>/services/loader.py` -> `get_catalog_item(..., definition_cls=...)`.
4. **Execution**: If executing steps, build `RunContext` and delegate to `run_steps` in `core.runtime.engine`.
5. **CLI**: Thin `commands/root.py`, Rich renderers in `cli/<x>/renderers.py`, plain-text formatters in `core/<x>/services/renderer.py`.

## Adding a new agent provider

**Relevant sources:** `src/worktree/core/agents/`, `src/worktree/core/config/models.py`

1. Add provider token to `AgentProvider` in `core/config/models.py` if not already present.
2. Select adapter pattern:
   - **Direct-mutation** (provider CLI/SDK directly edits files in sandbox — `cursor`, `gemini`, `copilot`): Subclass `CliDirectMutationAdapter` (`core/agents/cli_mutation.py`) and implement `_preflight`, `_provider_name`, and `_default_run`.
   - **Diff-returning** (provider returns diff text — `local`, `ollama`): Implement `AgentAdapter.propose_fix` directly (`core/agents/base.py`).
3. Resolve secrets via module-level `resolve_<provider>_api_key()` from environment variables (never from `config.json`).
4. Register in `get_agent_adapter` (`core/agents/factory.py`).
5. Add tests under `tests/core/agents/test_<provider>.py` with fake execution functions or transports.

## Secrets handling

**Relevant sources:** `src/worktree/core/agents/`

- API keys (`CURSOR_API_KEY`, `GEMINI_API_KEY`, `GH_TOKEN`, `GITHUB_TOKEN`) are resolved from the environment at call time.
- Secrets are never accepted as `config.json` fields, never persisted to `data.db`, and never passed into prompt builders.

## The `.worktree/` directory

Created and repaired idempotently by [core/bootstrap](../../src/worktree/core/bootstrap/):

```
.worktree/
  .meta/bootstrap.json
  .lock                       # cross-process advisory lock
  config.json                 # schemas/v1/config.json
  catalog/                    # workflows/, tasks/, steps/ + seeded wt/ templates
  sessions/                   # per-session artifacts (e.g. diff.patch)
  artifacts/, tmp/, logs/
  sandboxes/                  # git worktree checkouts
  data.db                     # SQLite database (core/db)
```

### Local SQLite (`data.db`)

**Relevant sources:** `src/worktree/core/db/`

- Migrated by `init_database` in `core/db/connection.py`.
- Repositories: `SandboxesDb`, `RunsRepository`, `CatalogDb`, `CostsDb` accessed via `WorktreeDb` facade.
- Construct repositories/facades once per command invocation rather than per query.

## Sandboxes (core)

**Relevant sources:** `src/worktree/core/sandbox/`, `src/worktree/core/sandbox/facade.py`

- Handled by `Sandbox` facade (`core/sandbox/facade.py`) and `core/sandbox/services/lifecycle.py`.
- On-disk location: `.worktree/sandboxes/<session_id>/`, branch `worktree/sandbox-<id>`.
- Operations: `create`, `list`, `show`, `delete`, `prune`, `apply`, `diff`.

## Packaged resources

Schemas (`schemas/v1/`) and catalog templates (`core/catalog/templates/`) ship inside the package and are loaded via `importlib.resources` at runtime.
