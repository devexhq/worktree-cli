# core/ Domain Restructure Plan (workflows, step, agents)

Status: **planning only** — no source files have been changed yet.

## Goal

Adopt a consistent, flat, domain-based module convention across `core/<domain>/`:

- `models.py` — every Pydantic `BaseModel` and `StrEnum` for the domain, including
  entity models *and* the `<Op>Status`/`<Op>Result` pairs currently scattered
  across operation files.
- `validators.py` — free functions used by `field_validator`/`model_validator`
  bodies in `models.py`, extracted out of `models.py`.
- `exceptions.py` — every raised `Exception` subclass for the domain.
- `services/<verb>.py` — operation modules containing only functions, no
  class/enum/exception definitions.

This plan applies the convention to `core/workflows/`, `core/step/`, and a new
`core/agents/` domain (split out of `core/workflows/agents/`, since agents will
eventually be used by `tasks` too, not just `workflows`).

### Confirmed decisions

1. `AgentAdapter` (currently a `Protocol` in `agents/base.py`) moves into
   `core/agents/models.py` alongside `AgentRequest`/`AgentResponse`, rather than
   a separate `interfaces.py`.
2. `core/workflows/discovery.py` and `core/workflows/inventory.py` merge into a
   single `core/workflows/services/discovery.py` — `build_workflow_inventory`
   is just `discover_workflow_files` + `parse_workflow_metadata` composed, not
   an independent concern.
3. `tests/core/workflows/test_workflow_discovery.py` and
   `test_workflow_inventory.py` merge into one `test_workflow_discovery.py`,
   mirroring the merged service.

## Finalized structure

```
core/workflows/
  __init__.py
  models.py       # WorkflowDefinition, StepAssert, WorkflowInput, StandardStepDefinition, LoopStepBlock
                  # + WorkflowDiscoveryStatus/Result, WorkflowInventory*, WorkflowMetadataStatus/ParseResult/ListMetadata,
                  #   WorkflowResolveStatus/Result, WorkflowValidationStatus/Result, WorkflowSeedResult
  validators.py   # _is_unsafe_assert_path, _validate_assert_paths (used by StepAssert validators)
  exceptions.py   # WorkflowError, WorkflowLoadError, WorkflowValidationError
  services/
    discovery.py  # resolve_workflows_dir, discover_workflow_files, build_workflow_inventory (merged discovery+inventory)
    metadata.py   # parse_workflow_metadata
    resolve.py    # resolve_workflow_by_name
    validate.py   # validate_workflow_document/_result, load_workflow_definition, validate_workflow_inputs
    seeder.py     # seed_starter_workflows
    render.py     # format_workflow_run_* failure bodies

core/step/
  __init__.py
  models.py       # StepDefinition, StepType, FailureAction
  validators.py   # parse_step_type / parse_failure_action coercion bodies
  exceptions.py   # StepNotFoundError, StepValidationError
  services/
    schema.py     # load_step_definition, load_step_by_id
    runner.py     # existing runner logic

core/agents/                      # new domain, moved out of core/workflows/agents/
  __init__.py
  models.py       # AgentRequest, AgentResponse, AgentResponseStatus, AgentAdapter (Protocol)
                  # + AgentFailurePayload, PayloadFile, PayloadOmission (moved from workflows/payload.py)
  exceptions.py   # MutationGitError
  services/
    factory.py
    cli_mutation.py
    mutation_git.py
    copilot.py
    cursor.py
    gemini.py
    local.py
    ollama.py
```

## Phase 1 — `core/workflows/`

1. `models.py` gains: `WorkflowDiscoveryStatus/Result`, `WorkflowInventory{Status,Result,ValidEntry,InvalidEntry}`,
   `WorkflowMetadataStatus/ParseResult/ListMetadata`, `WorkflowResolveStatus/Result`,
   `WorkflowValidationStatus/Result`, `WorkflowSeedResult`.
2. `validators.py` (new): `_is_unsafe_assert_path`, `_validate_assert_paths` extracted out of `models.py`.
3. `exceptions.py` unchanged (`WorkflowError`, `WorkflowLoadError`, `WorkflowValidationError`).
4. `services/discovery.py` (new, merged): `resolve_workflows_dir`, `discover_workflow_files`,
   `build_workflow_inventory` — combines current `discovery.py` + `inventory.py`, models stripped out.
   Delete `inventory.py`.
5. `services/metadata.py`, `services/resolve.py`, `services/validate.py`, `services/seeder.py`,
   `services/render.py` — moved as-is, model/enum/exception defs stripped.
6. `payload.py` (`AgentFailurePayload`, `PayloadFile`, `PayloadOmission`) **moves out entirely** to
   `core/agents/models.py` — it's only consumed by the agent adapter contract.

## Phase 2 — `core/step/`

1. `models.py`: `StepDefinition`, `StepType`, `FailureAction`.
2. `validators.py` (new): `parse_step_type`/`parse_failure_action` coercion bodies.
3. `exceptions.py` (new): `StepNotFoundError`, `StepValidationError` moved out of `schema.py`.
4. `services/schema.py`: `load_step_definition`, `load_step_by_id`.
5. `services/runner.py`: existing `runner.py` relocated.

## Phase 3 — `core/agents/` (new domain, replaces `core/workflows/agents/`)

1. `models.py`: `AgentRequest`, `AgentResponse`, `AgentResponseStatus`, `AgentAdapter` (Protocol) +
   `AgentFailurePayload`, `PayloadFile`, `PayloadOmission` (moved in from `workflows/payload.py`).
2. `exceptions.py` (new): `MutationGitError` moved out of `mutation_git.py`.
3. `services/`: `factory.py`, `cli_mutation.py`, `mutation_git.py`, `copilot.py`, `cursor.py`,
   `gemini.py`, `local.py`, `ollama.py`.

## Phase 4 — repoint every consumer

Confirmed via grep, these need import paths updated (submodule imports, not just
`workflows/__init__.py` re-exports):
i
- `getworktree/cli/init/{command,models,renderers}.py`, `getworktree/cli/workflow/command.py`,
  `getworktree/core/bootstrap.py` → `core.workflows.services.*`
- `getworktree/core/step/__init__.py`, `runner.py` → `core.step.services.schema`
- `getworktree/core/workflows/__init__.py` → full re-export rewrite
- All 6 files in `tests/core/workflows/agents/` + `agents/base.py` → `core.agents.models` /
  `core.agents.services.*`; directory moves to `tests/core/agents/`
- `tests/core/workflows/test_workflow_{metadata,render,resolve,seeder,validate}.py`,
  `tests/core/step/test_schema.py`, `tests/cli/init/test_init_*.py`,
  `tests/cli/workflow/test_workflow_run_command.py` → updated import paths
- `tests/core/workflows/test_workflow_discovery.py` + `test_workflow_inventory.py` → merged into one
  `test_workflow_discovery.py`

## Phase 5 — docs

Update [docs/agents/architecture.md](docs/agents/architecture.md) layer diagram, domain ownership,
import-direction rule (add `core/agents/`), and the Patch validation / Failure payload models /
Agent adapter sections that currently point at `core/workflows/agents/*` and `core/workflows/payload.py`.

## Phase 6 — verification

- `ruff format .`
- `ruff check .`
- `uv run inv test -c` (coverage ≥ 80%)
- `uv run inv complexity --paths <touched files> --plain` (no function > 10)
- Final grep for stale `core.workflows.agents` / `core.workflows.payload` /
  `core.workflows.discovery` / `core.workflows.inventory` references

## Open items / not yet in scope

- Whether the same convention (`models.py`/`validators.py`/`exceptions.py`/`services/`) should also be
  applied to `core/catalog/`, `core/config/`, `core/templates/` — not yet approved, to be decided
  after `workflows`/`step`/`agents` land.
