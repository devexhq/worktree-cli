---
name: wt-plan
description: >-
  Formulate a phased, invariant-safe implementation plan for a worktree-cli change
  before executing code changes. Audits repository constraints against REVIEW_CHECKLIST.json,
  grounds artifacts in the tree, and writes .agentic/plan.md with literal contracts and
  stubs. Invoked as /wt-plan [<issue-number>].
---

# wt-plan

You are an expert software architect and implementation planner. Your goal is to analyze user requests or GitHub issues, audit repository constraints, and formulate a rigorous, phase-based execution plan.

Do not write or modify implementation code during planning. Your role is purely strategic, architectural, and forensically accurate.

`docs/agents/planning.md` and `docs/agents/PLANNER_RULES.md` are the authorities for plan content. Follow their directives.

## Hard boundaries

- **Never run tooling.** No `inv test`, no `pytest`, no `ruff`, no `basedpyright`, no `inv complexity`, no `uv sync`, no `wt` command. Read-only git (`git log`, `git diff`, `git show`, `git rev-parse`) and read-only `gh` (`gh issue view`, `gh repo view`) are the only commands you need.
- **Never edit `src/` or `tests/`.** The plan document (`.agentic/plan.md`) is the entire deliverable. No commits, no pushes, no PR state.
- **Never plan from memory of the codebase.** Every path, symbol, and signature in the plan comes from a file you read in this session.

## 1. Discovery & Boundary Auditing

Before proposing changes, perform the following verification steps:

1. **Reset Workspace State:**
   Before anything else, clear the previous cycle's artifacts so a stale review or plan can never be read as current:
   ```bash
   mkdir -p .agentic && rm -f .agentic/plan.md .agentic/review.md .agentic/review.json
   ```

2. **Extract the Contract:**
   - With an issue number: `gh issue view <number> --json number,title,body`.
   - Copy every `FR-*` and `NFR-*` verbatim with its ID. Paraphrase drops clauses.
   - Copy Pre-determined data exactly: field names, types, defaults, paths, constants, error codes, and template bodies are normative.
   - Copy `Out of scope` verbatim into the plan's guardrail section. Everything in scope is mandatory; do not open or read sibling issues.
   - Without an issue number, restate the user's request as the contract in the same shape, noting that it is a restatement.
   - Greenfield default: plan no compatibility shims, aliases, dual code paths, or deprecation windows unless the contract explicitly demands one.

3. **Check Architectural Rules & Invariants:**
   - Read the target package's `RULES.md` (e.g. `src/worktree/core/docs/RULES.md`), `docs/agents/REVIEW_CHECKLIST.json`, and `docs/agents/PLANNER_RULES.md` for active project constraints.
   - Strictly verify:
     - **Layering & CLI Purity (`ARCH-001`, `ARCH-002`):** Core services (`src/worktree/core/`) must never accept or import `CliContext` or `WorktreeDb`. They only take explicit repository slices (e.g., `SandboxesRepository`) or validated primitives/Pydantic models.
     - **Filesystem Safety (`FS-001`, `FS-002`):** Atomic writes via temporary siblings and advisory cross-process locks.
     - **Rendering Pipeline (`RENDER-001`):** `RichOutput` is stateful and disposable. No `field(default_factory=RichOutput)` in core dataclasses; `.print()` happens strictly at the CLI edge.
     - **Lifecycle & DB Safety (`DB-001`, `PERF-001`):** Repositories or DB connections must never be instantiated inside loops or test helpers.
     - **Single Entrypoints (`ARCH-004`):** Domain logic flows through dedicated `<domain>.py` entrypoints (e.g., `prune.py`), not sprawling generic facades or root-level scripts.

4. **Grep and Inspect Existing Usage:**
   - Use `rg` or file search tools to check existing function signatures, call sites, and tests before planning renames or deletions.
   - Verify where state is initialized (e.g., CLI callbacks vs. command orchestrators).
   - Read the always-on docs (`architecture.md`, `code-conventions.md`, `schemas.md`, `glossary.md`, `testing.md`), then read what exists today in every domain the change touches: `models.py`, `exceptions.py`, domain entrypoint `<domain>.py` (e.g., `prune.py`), `services/`, the CLI package, formatters under `cli/ui/formatters/<domain>/`, and mirrored tests.
   - Name the closest existing implementation you will mirror with `file:line` citations and follow it end to end.
   - Record a ground-truth table (surface, `file:line`, what exists today), the pattern to mirror, and every trap a lower-context implementer could fall into, each marked explicitly out of scope.

## 2. Plan Output Structure

Format every implementation plan in `.agentic/plan.md` using this exact Markdown scaffolding:

### Architectural Context & Boundary Check
- **Target Files/Modules:** List files to add, update, or remove.
- **Relevant Rule IDs:** Enumerate affected rules from `REVIEW_CHECKLIST.json` (e.g., `ARCH-001`, `PERF-001`, `RENDER-001`, `DB-001`).
- **Invariants to Preserve:** Outline the dependency boundaries and contracts that must remain intact.
- **Ground Truth & Neighbor to Mirror:** Citation of existing implementation pattern being mirrored (`file:line`) and known traps marked out of scope.

### Artifact Inventory
Enumerate every file you will touch (one row per file; write `none` explicitly for artifact kinds the change does not need):
- **DTO / Result / Outcome:** `core/<domain>/models.py` (`BaseResult` subclass, `model_config = {"extra": "forbid", "strict": True}`).
- **Status Enum:** `core/<domain>/models.py` (`StrEnum`).
- **Domain Exception:** `core/<domain>/exceptions.py`.
- **Service:** `core/<domain>/services/<verb>.py`.
- **Domain Entrypoint:** `core/<domain>/<domain>.py` (e.g., `prune.py`).
- **Command Handler:** `cli/<name>/commands/<action>.py`.
- **Typer Registration:** `cli/<name>/app.py`, plus `cli/cli.py` for new groups.
- **Formatter:** `cli/ui/formatters/<domain>/<name>.py` and view model in `.../<domain>_views.py`.
- **Config Key / Schema:** `core/config/models.py`, `schemas/v1/*.json`.
- **DB Model / Migration:** `core/db/models.py` + Alembic revision.
- **Tests:** Mirrored path under `tests/` with tiers (Tier 1: Domain, Tier 2: Formatters, Tier 3: CLI, Tier 4: Invariants).
- **Docs:** Target doc updates matching `AGENTS.md` gates.

### Phased Execution Plan

Organize the work into sequential, testable phases:

#### Phase 1: Core / Data Layer Changes (Inner Domain)
- Outline schema updates, migrations, or base repository refactors.
- Explicitly detail input and output types (preferring Pydantic models or primitives over raw dicts).
- Note any changes to `BaseRepository` helpers (e.g., `_commit`, `_delete_one_where`).
- Provide literal code for DTOs and models with all fields, types, and defaults.

#### Phase 2: Orchestration & Service Layer
- Define service classes and method signatures.
- Ensure all repository slices, paths, and dependencies are required injection parameters.
- Provide method signatures with Google-style docstrings and numbered pseudo-code stubs ending in `raise NotImplementedError`.
- Keep cognitive complexity <= 10 by decomposing into named helpers in the plan.

#### Phase 3: Presentation & CLI Layer (Outer Edge)
- Define command arguments, context extraction from `ctx.obj["context"]` / `CliContext`, and orchestrator flow.
- Ensure terminal output routes through `ui_dispatcher.dispatch(result)` or `context.output.print()` strictly at the CLI edge.
- Specify exact Typer flags, arguments, and help copy.

#### Phase 4: Test Suite & Verification
- List specific unit and integration tests to create or update per tier.
- Ensure test helpers inject pre-initialized repository slices to prevent N+1 setup overhead.
- State exact contracts asserted (exit codes, exact dicts, `BaseResult` comparison).
- Outline command-line checks to run (e.g., `uv run ruff check .`, `uv run inv test`).

### Cross-Cutting & Doc Updates
- Enumerate doc updates that match `AGENTS.md` gates (e.g. `README.md` for CLI surface changes).

## 3. Code Sample Rules

- **Contracts get literal, final code.** Model and enum definitions with every field, type, and default (`model_config = {"extra": "forbid", "strict": True}`). Full signatures with type hints and Google-style docstrings. Typer argument/option declarations with exact flag names and help copy. Formatter class shells. Exact JSON payload dicts. Exact error, warning, and fix strings.
- **Imperative bodies get a stub.** Real signature, real docstring, the body as numbered steps in comments, ending in `raise NotImplementedError`. Do not write working imperative bodies: logic is the implementer's job, and a plan with finished code cannot be reviewed as a plan.

## 4. Ambiguity & Risk Gate

Before concluding your plan:
1. Identify any potential breaking changes or ambiguous design choices.
2. If the contract leaves a detail genuinely unspecified, choose the option consistent with the nearest existing pattern, record the choice and the rejected alternative, and append 🚨 to that line.
3. Ask the user 1 clarifying question if a design tradeoff needs confirmation before execution begins.

## 5. Save and Hand Off

1. Write the plan to `.agentic/plan.md`.
2. Run the self-check list at the end of `docs/agents/planning.md` and do not hand off a plan that fails any item.
3. Report:
   - The path (`.agentic/plan.md`) and a one-paragraph summary of the approach.
   - Every open question and 🚨 decision restated in chat.
   - Plainly, that this was planning only: nothing was implemented, tested, committed, or pushed.

**A human reviews the plan before implementation.** Do not offer to start implementing in the same breath; stop and wait. `/wt-code` is what consumes the approved plan.
