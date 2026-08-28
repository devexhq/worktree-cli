# Glossary

Short definitions for terms this codebase uses precisely. Each points at the
model/package that owns it — read there for the exact shape rather than
treating this list as a second source of truth for field-level detail.

- **Step** — the smallest executable unit: a command, agent prompt, or script,
  with an optional `assert` block and `on_failure` policy. Model:
  `StepDefinition` ([schemas-and-config.md](schemas-and-config.md#stepdefinition-model)).
  Runner: `StepExecution.run`.
- **Loop step** — a step-list wrapper that repeats its `do: []` steps until a
  condition or `max_iterations`. Model: `LoopStepBlock`. Executed in workflows
  via `LoopBlockRunner` in `core/runtime/`.
- **Task** — a blueprint document with `steps: list[StepDefinition]` (no loop
  steps allowed) and declared `inputs`. Model: `BlueprintDefinition(kind=task)`
  (`core/blueprint/models.py`).
- **Workflow** — a blueprint document like a task but allowed to contain loop
  steps. Model: `BlueprintDefinition(kind=workflow)` (`core/blueprint/models.py`).
- **Blueprint** — the unifying term for "task or workflow document." In code,
  specifically `BlueprintDefinition` / `Blueprint` (`core/blueprint/`), the live
  model/handle that superseded separate task and workflow models — not just an
  informal synonym for "task or workflow."
- **Catalog** — the on-disk registry of named workflows/tasks/steps under
  `.worktree/catalog/{workflows,tasks,steps}/`, plus packaged seed templates.
  Owner: `core/catalog/` (`Catalog`, `get_catalog_item`, seeding services).
- **Run** — one execution of a blueprint's steps, from `run_steps` starting to
  its terminal `RunOutcome`. Not itself a dedicated model — see **run
  context** / **run outcome** / **session**.
- **Run context** — the immutable input bundle for one run (`RunContext`):
  steps, cwd, sandbox/interactive options, and (when resuming) the checkpoint
  to resume from.
- **Run outcome** — the terminal result of a run (`RunOutcome`): status, step
  results, warnings, and (when stamped by `Engine`) a session id.
- **Session** (session id) — the string identifier tying a run to a row in
  `data.db`'s runs table, minted by `Engine.run` (`{kind}_{8-hex}` by default)
  or supplied by the caller. `wt history` and `wt resume` key off this id, not
  the blueprint name.
- **Sandbox** — an isolated git worktree checkout a run executes inside
  (`.worktree/sandboxes/<session_id>/`, branch `worktree/sandbox-<id>`),
  created/cleaned by `GitSandboxManager`. A run can opt out
  (`use_sandbox=False`) and execute directly in the repo's working directory
  instead.
- **Checkpoint** — the JSON-serializable pause payload (`RunCheckpoint`) that
  lets a `prompt_user`-paused run resume later: pending step, completed step
  results, sandbox identity, and run options. Persisted via a `RunPauseStore`
  implementation into the runs table's `checkpoint_json` column.
- **Kind** (`BlueprintKind`) — the `task` | `workflow` discriminator on a live
  `BlueprintDefinition`. Injected by `Blueprint.load` / `from_document`, never
  authored in YAML.
- **Input** (parameter input) — a typed, optionally-required,
  optionally-defaulted parameter a blueprint declares (`ParameterInput`) and
  steps reference via `${{ inputs.<name> }}`. See
  [schemas-and-config.md](schemas-and-config.md#inputs-and-interpolation).
- **Engine** — ambiguous on its own; two unrelated things share the name (see
  [architecture.md](architecture.md#layers)'s naming-hazard note):
  - `core/engine/engine.py`'s `Engine` class — the live process facade
    (`Engine.run` / `Engine.resume`) that persists a run row and calls
    `run_steps`.
  - `core/runtime/engine.py`'s module-level `run_steps` function — the actual
    step-loop/sandbox orchestration `Engine` (the class) delegates to.

  When in doubt, say "the `Engine` class" or "`run_steps`" instead of "the
  engine."
- **Adapter** (agent adapter) — a provider-specific implementation of
  `AgentAdapter.propose_fix` — `local`, `ollama`, `cursor`, `gemini`,
  `copilot`. See
  [architecture.md](architecture.md#adding-a-new-agent-provider).
