# Architecture

Structural map for agents. **File placement rules** (where models vs services
live) are in
[code-conventions.md — Core package layout](code-conventions.md#core-package-layout).
User-facing command behavior lives under [docs/cli/](../cli/). YAML/config field
detail lives in [schemas-and-config.md](schemas-and-config.md).

## Layers

```
src/worktree/cli/cli.py              Typer entrypoint
src/worktree/cli/<name>/             One package per CLI subcommand (thin wrappers over domain)
  app.py                             Typer app / command registration
  commands/                          Command handlers (e.g. root.py, show.py)

src/worktree/core/                   Business logic (no Typer)
  bootstrap.py                       .worktree/ create/repair
  git_sandbox.py                     git worktree sandbox lifecycle
  config/                            Legacy flat infra (loader/mutate/validate/…)
  db/                                Legacy flat infra (connection, migrations, repos)
  inputs/                            models.py + services/ (resolve, interpolate, renderer)
  catalog/                           models.py + services/ + templates/
  blueprint/                         models.py, blueprint.py (load/inspect handle)
  history/                           models.py, renderers.py, services.py
  step/                              models.py, exceptions.py, runner.py (entrypoint),
                                     assertions/, services/{loader,resolver}.py
  runtime/                           models.py, exceptions.py, engine.py (entrypoint),
                                     failure + pause helpers
  engine/                            models.py, engine.py (process facade)
  task/                              models.py, exceptions.py, services/{loader,runner,renderer}.py
  agents/                            models.py + adapters (base, factory, providers)
  patch/                             models.py, exceptions.py, patch.py (entrypoint)
  workflows/                         models.py, exceptions.py, services/

src/worktree/common/                 Shared helpers (no core/ imports)
src/worktree/schemas/v1/             Versioned JSON Schemas
```

Default for **new** domain code: `models.py` + `services/<verb>.py`. Do not
extend the flat `config/` / `db/` pattern to new domains. See
[code-conventions.md](code-conventions.md#core-package-layout).

Single-step execution: `core/step/` (`runner.py`). Multi-step orchestration:
`core/runtime/` (`engine.py` → `run_steps`). Process facade: `core/engine/`
(`Engine.run` / `Engine.resume`).

### Domain ownership

- **Task** (`core/task/`): `TaskDefinition`, catalog loader, `run_task` adapter,
  plain-text failure renderers.
- **Inputs** (`core/inputs/`): `ParameterInput`, CLI resolve, `${{ inputs.* }}`
  interpolation. Must not import step/runtime/task/workflows/agents/patch.
- **Step** (`core/step/`): `StepDefinition`, `StepAssert` / assertions,
  `execute_step`, failure policy types used by blueprints. Must not import
  runtime/task/workflows.
- **Agents** (`core/agents/`): adapter protocol, provider implementations,
  and failure payload models. Must not import step/runtime/task/workflows.
- **Patch** (`core/patch/`): unified-diff parse/validate (no git apply).
  Must not import agents/step/runtime/task/workflows.
- **Blueprint** (`core/blueprint/`): unified task/workflow document handle,
  catalog/path load, and `resolve_inputs` against declared parameters.
- **Runtime** (`core/runtime/`): `run_steps`, `RunContext` / `RunObserver` /
  `RunOutcome`, in-process failure orchestration after a failed step
  (stop / `prompt_user` / retry-or-continue), and durable pause via
  `RunPauseStore` / `RunCheckpoint` hooks. Step-local retry stays in step.
  `RunOutcome.session_id` may be stamped by Engine; `run_steps` does not mint
  it. Runtime must not import task/workflow DB facades or `cli/`.
- **Engine** (`core/engine/`): `RunRequest`, persist run row, mint session id,
  resolve inputs before `run_steps`, stamp `session_id` on `RunOutcome`.
  Must not import `cli/`.
- **Workflows** (`core/workflows/`): workflow definition models and
  `resume_workflow` (rebuilds `RunContext` from a paused checkpoint and
  re-enters `run_steps`). Sibling of task — neither imports the other.
  Domain adapters persist pause checkpoints.
- **Catalog** (`core/catalog/`): blueprint scan/index, `CatalogDb` sync hooks,
  packaged seeds under `templates/`.
- **History** (`core/history/`): `HistoryListService`, `HistoryShowService`,
  result models, and table/panel renderers.
- **Shared core infra**: `config/`, `db/`, `bootstrap.py`, `git_sandbox.py`,
  plus foundational domains above.

CLI: packages are thin wrappers over core domain services and contain no
business logic, database queries, or execution algorithms.

### Package boundaries (import direction)

Dependencies flow one way; do not import "up" the stack:

```
common/  ->  core/{db,catalog,inputs,patch,history}/  ->  core/agents/  ->  core/step/  ->  {core/runtime/, core/blueprint/}  ->  core/engine/  ->  {core/task/, core/workflows/}  ->  cli/
```

- `common/` never depends on `core/`.
- `core/inputs/` must not import `step`, `runtime`, `task`, `workflows`,
  `agents`, or `patch`.
- `core/patch/` must not import `agents`, `step`, `runtime`, `task`, or
  `workflows`.
- `core/agents/` may use `patch/` and `config/`; must not import `step`,
  `runtime`, `task`, or `workflows`.
- `core/step/` must not import `runtime`, `task`, or `workflows` for shared
  vocabulary — put shared types in `common/` or `step/`. Agent dispatch uses
  `core.agents` from the step runner.
- `core/runtime/` may use `step/`, `db/`, `git_sandbox.py`; must not import
  `blueprint/`, `engine/`, `task/`, `workflows/`, or `cli/`.
- `core/blueprint/` may use `catalog/`, `inputs/`, `step/`; must not import
  `runtime/`, `engine/`, `task/`, `workflows/`, or `cli/`.
- `core/engine/` may use `runtime/`, `blueprint/`, `db/`; must not import
  `task/`, `workflows/`, or `cli/`.
- `core/task/` and `core/workflows/` depend on runtime/step/inputs/catalog;
  they do not import each other.
- `cli/` may import `core/` and `common/`; those layers never import `cli/`.

If a lower package needs a type from a higher one, **move the type down**
instead of adding an upward import.

## Adding a new command

1. Create `src/worktree/cli/<name>/` with lean `app.py` and `commands/<subcommand>.py` (or
   `commands/root.py` for root commands).
2. Wire command logic directly to underlying domain services (e.g. `BlueprintRunService`,
   `HistoryListService`). The CLI package should not contain actual logic — it is
   simply a wrapper around the domain being executed.
3. Register in [src/worktree/cli/cli.py](../../src/worktree/cli/cli.py).
4. Tests under `tests/cli/<name>/`.

## Adding a new catalog-backed domain

When creating or refactoring a blueprint domain (e.g. `task`, `workflow`, `step`):

1. **Models**: `<X>Definition` in `core/<x>/models.py`.
2. **Exceptions**: `<X>LoadError` / `<X>ValidationError` subclassing the common
   definition errors in `core/<x>/exceptions.py`.
3. **Loader**: `core/<x>/services/loader.py` → thin
   `get_catalog_item(..., definition_cls=...)`.
4. **Execution**: if it runs steps, build `RunContext` and call
   `run_steps` in `core.runtime.engine` — no duplicate step loops/sandbox
   lifecycle.
5. **CLI**: thin `command.py`; Rich in `cli/<x>/renderers.py`; plain-text
   formatters in `core/<x>/services/renderer.py`. No production test-seam
   parameters (`execute_fn=...`).

## The `.worktree/` directory

Created/repaired by
[bootstrap.py](../../src/worktree/core/bootstrap.py) (idempotent; never deletes
user data):

```
.worktree/
  .meta/bootstrap.json
  config.json                 # schemas/v1/config.json
  catalog/                    # workflows/, tasks/, steps/ + seeded wt/ templates
  workflows/                  # legacy bootstrap dir
  sessions/                   # per-session artifacts (e.g. diff.patch)
  artifacts/, tmp/, logs/
  sandboxes/                  # git worktree checkouts
  data.db                     # SQLite (core/db)
```

Catalog dirs/seeds: `core/catalog` (`ensure_catalog_dirs`,
`scan_and_index_catalog`, `seed_all_catalog_templates`).

### Local SQLite (`data.db`)

Migrated by `init_database` in [core/db](../../src/worktree/core/db/__init__.py).
Typed surface: `DbBase`, repos (`SandboxesDb`, `RunsDb`,
`CatalogDb`, `CostsDb`), facade `WorktreeDb` (`.sandboxes`, `.runs`, …).

Primary tables include sandbox metadata, catalog index rows, run tracking, and
workflow cost rows. Schema evolution stays in `core/db` migrations — do not
document every column here; read models in `core/db/models.py`.

## Sandboxes (core)

[GitSandboxManager](../../src/worktree/core/git_sandbox.py) owns create/cleanup
and best-effort `SandboxesDb` writes.

- On-disk: `.worktree/sandboxes/<session_id>/`, branch `worktree/sandbox-<id>`.
- Result API: `create_sandbox_result` → `SandboxCreateResult` (warnings do not
  flip `ok`). `cleanup_sandbox` is idempotent.
- CLI UX (`wt sandbox create|list|show|delete`): [docs/cli/sandbox.md](../cli/sandbox.md).

## Workflows, agents, patches

| Concern | Where |
|---------|--------|
| Workflow YAML / `wt workflow *` | [docs/cli/workflow.md](../cli/workflow.md), [schemas-and-config.md](schemas-and-config.md) |
| Task YAML / `wt task *` | [docs/cli/task.md](../cli/task.md), schemas-and-config |
| Patch validation | `core/patch/` (`validate_patch_text`) |
| Agent failure payload DTOs | `core/agents/models.py` |
| Agent adapters | `core/agents/` — protocol + `local` / `ollama` / `cursor` / `gemini` / `copilot` |
| `wt workflow run` | Validate/load path today; full execution is incremental on the shared runtime — see open issues, not a second engine here |

Provider-specific env vars and stdout contracts belong in code docstrings or
CLI docs when user-visible — not as growing appendices in this file.

## Packaged resources

Schemas and catalog templates ship in the wheel and are loaded via
`importlib.resources` (see `common/schema_validation.py`, workflow validators,
`core/catalog/templates/`), not repo-relative paths at runtime.
