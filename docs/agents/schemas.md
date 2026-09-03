# Schemas and Entities

Comprehensive reference for the shape of entities across the Worktree CLI codebase: exceptions, DTOs, domain facades, CLI commands, and JSON/YAML schemas.

---

## 1. Exception Hierarchy and Domain Errors

**Relevant sources:**
- `src/worktree/common/exceptions.py`
- `src/worktree/common/lock.py`
- `src/worktree/core/*/exceptions.py`

### Base Definition Exceptions
- `DefinitionError` (`common/exceptions.py`): Base exception for catalog-backed domain definitions.
- `DefinitionNotFoundError` (`common/exceptions.py`): Definition file or identifier not found.
- `DefinitionLoadError` (`common/exceptions.py`): YAML syntax or parse failure when reading definition.
- `DefinitionValidationError` (`common/exceptions.py`): Schema or Pydantic validation failure.

### Domain Exceptions
- **Blueprint** (`core/blueprint/exceptions.py`):
  - `BlueprintNotFoundError` (subclasses `DefinitionNotFoundError`)
  - `BlueprintLoadError` (subclasses `DefinitionLoadError`)
  - `BlueprintValidationError` (subclasses `DefinitionValidationError`)
- **Step** (`core/step/exceptions.py`):
  - `StepNotFoundError` (subclasses `DefinitionNotFoundError`)
  - `StepValidationError` (subclasses `DefinitionValidationError`)
- **Catalog** (`core/catalog/exceptions.py`):
  - `CatalogError`: Base catalog exception.
  - `CatalogFileNotFoundError`: Specified catalog resource not on disk.
  - `CatalogYamlError`: YAML syntax error when parsing catalog item.
  - `CatalogWriteError`: File write or permission failure during catalog mutation.
- **Config** (`core/config/exceptions.py`):
  - `ConfigLoadError`: Fatal configuration loading failure.
- **Engine** (`core/engine/exceptions.py`):
  - `EngineError`: Base process engine error.
  - `EngineRuntimeError`: Execution runtime error.
  - `EngineInputError`: Input resolution failure before run creation.
  - `EngineResumeError`: Incompatible or invalid run state during resume.
- **Git** (`core/git/exceptions.py`):
  - `GitError`: Base Git failure.
  - `GitCommandError`: Non-zero exit code from git subprocess.
  - `GitNotFoundError`: Binary missing or repository root not found.
  - `GitPlumbingTimeoutError`: Git plumbing operation timed out.
- **Sandbox** (`core/sandbox/exceptions.py`):
  - `SandboxError`: Base sandbox failure.
  - `SandboxConfigError`: Invalid sandbox configuration parameters.
  - `SandboxCapacityError`: Active sandbox limit reached.
- **Runtime** (`core/runtime/exceptions.py`):
  - `PromptUserInterruptedError`: User aborted interactive failure prompt (e.g. Ctrl-C after checkpoint persisted).
- **Patch** (`core/patch/exceptions.py`):
  - `MalformedDiffHeader`: Invalid unified diff format.
- **Lock** (`common/lock.py`):
  - `LockTimeoutError`: Timeout acquiring `.worktree/.lock` advisory lock.

---

## 2. DTOs, Results, and Outcome Models

**Relevant sources:**
- `src/worktree/core/*/models.py`
- `src/worktree/common/models.py`

### Result/Outcome Pattern
All operations that can fail return a Pydantic result object instead of raising:
- `status: StrEnum`: Machine-readable outcome state.
- `errors: list[str]`: Fatal error messages (empty on success).
- `warnings: list[str]`: Non-fatal warning messages.
- `ok: bool`: Property returning `True` when `not bool(self.errors)` or `status == OK`.
- Standard configuration: `model_config = {"extra": "forbid", "strict": True}`.

### Configuration Models
**Relevant sources:** `src/worktree/core/config/models.py`, `loader.py`, `validate.py`, `mutate.py`, `generator.py`.
- `WorktreeConfig`: Root configuration object (`version`, `project`, `paths`, `sandbox`, `agent`, `history`, `doctor`, `prune`, `telemetry`, `concurrency`).
- Section configs: `ProjectConfig`, `PathsConfig`, `SandboxConfig`, `AgentConfig`, `HistoryConfig`, `DoctorConfig`, `PruneConfig`, `TelemetryConfig`, `ConcurrencyConfig`.
- `ConfigLoadResult`: Result of loading and validating `.worktree/config.json` (`status`, `config_path`, `raw`, `config`, `errors`, `ok`).
- `ConfigValidationResult`: Result of semantic config validation (`status`, `config_path`, `raw`, `config`, `errors`, `warnings`, `ok`).
- `ConfigSetResult`: Result of mutating a dot-path key in config (`status`, `config_path`, `key`, `value`, `errors`, `ok`).
- `ConfigGenerationResult`: Result of creating, repairing, or overwriting config (`created`, `skipped_existing`, `repaired`, `overwritten`, `inserted_keys`, `warnings`, `errors`, `ok`).

### Blueprint & Step Models
**Relevant sources:** `src/worktree/core/blueprint/models.py`, `src/worktree/core/step/models.py`, `src/worktree/core/inputs/models.py`.
- `BlueprintDefinition`: Unified model for task and workflow blueprints (`id`, `name`, `description`, `kind`, `inputs`, `defaults`, `steps`, `use_sandbox`).
- `BlueprintKind`: `StrEnum` (`task`, `workflow`). Injected at load time; tasks cannot contain loop steps.
- `BlueprintDefaults`: Blueprint-level defaults (`on_failure`).
- `ParameterInput`: Declared parameter input (`type`, `description`, `required`, `default`, `aliases`).
- `InputResolveResult`: Result of resolving input values from CLI flags and defaults (`values`, `missing`, `errors`, `warnings`, `ok`).
- `StepDefinition`: Executable step specification (`id`, `name`, `type`, `description`, `command`, `prompt`, `script_path`, `tools`, `env`, `timeout_seconds`, `assert_`, `on_failure`, `uses`, `run`).
- `StepAssert`: Verification conditions (`exit_code`, `output_contains`, `output_not_contains`, `regex_match`, `json_match`, `file_exists`, `file_not_exists`, `file_not_empty`).
- `FailurePolicy`: `StrEnum` (`abort`, `continue`, `prompt_user`, `retry`). Terminal policies exclude `retry`.
- `FailureSpec`: Normalized failure policy (`action`, `max_retries`, `backoff_ms`, `on_max_retries`).
- `LoopStepBlock`: Step container repeating `do: []` until `until` condition or `max_iterations` (`id`, `type="loop"`, `max_iterations`, `until`, `do`, `on_max_iterations`).
- `StepResult`: Step execution outcome (`step_id`, `status`, `exit_code`, `stdout`, `stderr`, `duration_seconds`, `attempts`, `error_message`, `ok`).
- `AssertionResult`: Assertion evaluation outcome (`passed`, `failed_conditions`, `message`).

### Runtime & Process Engine Models
**Relevant sources:** `src/worktree/core/runtime/models.py`, `src/worktree/core/engine/models.py`.
- `RunContext`: Immutable execution input bundle (`steps`, `cwd`, `use_sandbox`, `keep`, `agent`, `observer`, `inputs`, `non_interactive`, `failure_prompter`, `pause_store`, `resume_from`).
- `RunOutcome`: Terminal run result (`status`, `step_results`, `errors`, `warnings`, `sandbox_kept`, `sandbox_path`, `session_id`, `ok`).
- `RunStatus`: `StrEnum` (`pending`, `running`, `completed`, `failed`, `paused`, `cancelled`).
- `RunCheckpoint`: JSON-serializable state for paused runs (`sandbox_path`, `sandbox_id`, `sandbox_branch`, `use_sandbox`, `keep`, `agent`, `inputs`, `pending_step_id`, `pending_result`, `diagnostic`, `next_step_index`).
- `RunRequest`: Facade execution parameters for `Engine.run` (`inputs`, `cli_args`, `use_sandbox`, `keep`, `agent`, `session_id`, `observer`, `failure_prompter`, `non_interactive`).
- `ResumableRun`: Non-raising inspector and loader for paused runs.
- `EngineResumeStatus`: `StrEnum` (`ok`, `not_found`, `wrong_status`, `missing_sandbox`, `corrupt_checkpoint`, `failed`).

### Agent Provider Models
**Relevant sources:** `src/worktree/core/agents/models.py`, `src/worktree/core/agents/cli_mutation.py`.
- `AgentRequest`: Input payload to agent adapter (`prompt`, `failure_payload`, `timeout_seconds`, `config`, `sandbox_path`).
- `AgentResponse`: Adapter outcome (`status`, `patch`, `errors`, `warnings`, `summary`, `ok`).
- `AgentResponseStatus`: `StrEnum` (`proposed_patch`, `no_op`, `unfixable`, `timeout`, `provider_error`).
- `AgentFailurePayload`: Step failure context captured for agent prompts (`step_id`, `command`, `exit_code`, `stdout`, `stderr`, `duration_seconds`, `error_message`, `files`).
- `CliMutationRunRequest`: Subprocess execution payload for direct-mutation adapters (`prompt`, `sandbox_path`, `timeout_seconds`, `env`).
- `CliMutationOutcome`: Direct-mutation subprocess result (`success`, `exit_code`, `stdout`, `stderr`, `error_message`).

### Sandbox Models
**Relevant sources:** `src/worktree/core/sandbox/models.py`.
- `SandboxSession`: Active sandbox metadata (`session_id`, `sandbox_path`, `target_branch`, `base_commit`, `created_at`, `status`).
- `SandboxCreateResult`: Result of creating sandbox worktree (`status`, `session_id`, `sandbox_path`, `branch_name`, `errors`, `warnings`, `ok`).
- `SandboxDeleteResult`: Result of deleting sandbox (`status`, `session_id`, `sandbox_path`, `branch_deleted`, `errors`, `warnings`, `ok`).
- `SandboxPruneResult`: Result of pruning stale/orphan sandboxes (`status`, `pruned_items`, `errors`, `warnings`, `ok`).
- `SandboxListResult`, `SandboxShowResult`, `SandboxApplyResult`, `SandboxDiffResult`, `SandboxDetectionResult`.

### Catalog Models
**Relevant sources:** `src/worktree/core/catalog/models.py`.
- `CatalogItem`: Indexed item metadata (`id`, `name`, `type`, `path`, `source`, `sha256`, `description`).
- `CatalogItemType`: `StrEnum` (`workflow`, `task`, `step`, `template`).
- `CatalogInventory`: Collection of scanned catalog items.
- `SeedResult`: Template seeding outcome (`created_files`, `skipped_existing_files`, `overwritten_files`, `warnings`, `errors`, `ok`).

### Database SQLModel Records
**Relevant sources:** `src/worktree/core/db/models.py`.
- `SandboxRecord`: Persisted sandbox rows in `sandboxes` table.
- `RunRecord`: Persisted blueprint run rows in `runs` table (including `checkpoint_json`).
- `CatalogRecord`: Persisted catalog index rows in `catalog_items` table.
- `CostRecord`: Persisted token and execution cost tracking in `costs` table.

### History, Diff, and Status Models
**Relevant sources:** `src/worktree/core/history/models.py`, `src/worktree/core/diff/models.py`, `src/worktree/core/status/models.py`.
- `HistoryListResult`, `HistoryShowResult`: History query results.
- `DiffResult`: Session unified-diff and artifact outcome (`status`, `diff_text`, `files_changed`, `errors`, `ok`).
- `WorktreeStatusResult`: Workspace health, repository status, and collected developer warnings.

---

## 3. Domain Facades

**Relevant sources:**
- `src/worktree/core/*/facade.py`
- `src/worktree/common/filesystem/facade.py`
- `src/worktree/core/engine/engine.py`
- `src/worktree/core/git/runner.py`

Each core domain exposes a cohesive facade class that encapsulates domain services, queries, and repositories:

| Facade | Module | Key Responsibilities & Methods |
|:---|:---|:---|
| `Bootstrap` | `core/bootstrap/facade.py` | Idempotent workspace initialization and repair (`ensure_workspace`, `initialize_workspace`). |
| `GitRunner` | `core/git/runner.py` | Low-level git CLI execution (`run`, `worktree_add`, `worktree_remove`, `worktree_list`, `diff`). |
| `Sandbox` | `core/sandbox/facade.py` | Worktree sandbox lifecycle (`create`, `show`, `list`, `delete`, `prune`, `apply`, `diff`). |
| `Config` | `core/config/facade.py` | Config loading, validation, generation, and mutation (`load`, `validate`, `set`, `generate`, `show`). |
| `WorktreeDb` | `core/db/facade.py` | Central database access point (`sandboxes`, `runs`, `catalog`, `costs` repositories). |
| `Inputs` | `core/inputs/facade.py` | Input flag parsing, default resolution, and placeholder interpolation (`parse_args`, `resolve`, `interpolate`). |
| `Catalog` | `core/catalog/facade.py` | Template scanning, indexing, retrieval, and seeding (`list_items`, `get_item`, `seed_templates`, `scan_and_index`). |
| `Blueprint` | `core/blueprint/facade.py` | Loading and rendering unified blueprint documents (`load`, `from_path`, `from_document`, `render_show`). |
| `Diff` | `core/diff/facade.py` | Session diff calculation, artifact loading, and rendering (`get_diff`, `render`). |
| `Status` | `core/status/facade.py` | Workspace health and telemetry aggregation (`collect`). |
| `History` | `core/history/facade.py` | Execution history query and display (`list_runs`, `get_run`). |
| `Step` | `core/step/facade.py` | Step blueprint load, resolution, and isolated execution (`load`, `resolve`, `execute`, `assert_step`). |
| `Engine` | `core/engine/engine.py` | Process-level run persistence, session minting, execution, and resume (`run`, `resume`, `reconcile`). |
| `Filesystem` | `common/filesystem/facade.py` | Atomic writes, safe path operations, and YAML parsing (`atomic_write_json`, `atomic_write_text`, `read_yaml`). |

---

## 4. Commands and CLI Surface

**Relevant sources:**
- `src/worktree/cli/cli.py`
- `src/worktree/cli/<name>/`

### Entrypoint and Global Options
- Application: `app = typer.Typer(cls=WorktreeTyperGroup, name="wt")` in `src/worktree/cli/cli.py`.
- Global options:
  - `-p, --path`: Workspace root directory.
  - `-v, --verbose`: Verbose telemetry logging.
  - `--version`: Print CLI version and exit.

### Subcommand Structure
Each CLI command package under `src/worktree/cli/<name>/` contains:
- `app.py`: Subcommand Typer app registration.
- `commands/`: Individual command implementations (e.g. `root.py`, `commands/<action>.py`) returning core domain `*Result` models.
- `formatters.py`: UI dispatcher component formatters for core domain `*Result` models.
- `renderers.py`: Rich-based terminal presentation functions.

### Registered CLI Commands
- `wt init`: Initialize workspace, generate `.worktree/` directory and `config.json`.
- `wt status`: Show workspace health, active sandboxes, and developer warnings.
- `wt config`: Manage configuration (`show`, `set`, `validate`).
- `wt catalog`: Manage catalog items (`list`, `show`, `create`, `delete`).
- `wt run`: Execute a task or workflow blueprint.
- `wt resume`: Resume a paused execution session.
- `wt sandbox`: Manage git worktree sandboxes (`create`, `list`, `show`, `delete`, `prune`, `apply`).
- `wt history`: Query past run records (`history`, `history show`).
- `wt diff`: Show uncommitted or session diffs.

---

## 5. JSON and YAML Schemas

**Relevant sources:**
- `src/worktree/schemas/v1/config.json`
- `src/worktree/schemas/v1/workflow.json`
- `src/worktree/common/schema_validation.py`

### Schema Contracts
- **Config V1 (`v1/config.json`)**:
  - Validates `.worktree/config.json`.
  - Enforces `additionalProperties: false` across all objects.
  - Required top-level keys: `version`, `project`, `paths`, `sandbox`, `agent`, `history`, `doctor`, `prune`, `telemetry`, `concurrency`.
  - Supported agent provider tokens: `local`, `ollama`, `cursor`, `gemini`, `copilot`, `openai`, `anthropic`, `azure_openai`, `custom`.
- **Workflow V1 (`v1/workflow.json`)**:
  - Validates workflow and task YAML definitions.
  - Enforces schema for `steps`, `inputs`, `defaults`, and `assert` blocks.
- **Validation Engine**:
  - Evaluated via `SchemaValidator` (`common/schema_validation.py`).
  - Wraps `jsonschema.Draft202012Validator` and returns a non-raising `ValidationResult(ok, errors)`.
