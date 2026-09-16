---
name: wt-plan
description: >-
  Formulate a phased, invariant-safe implementation plan for a worktree-cli change
  before executing code changes. Audits repository constraints against REVIEW_CHECKLIST.json,
  grounds artifacts in the tree, declares a test ledger with line budgets,
  declares what the change deletes, and writes the plan directly to .agentic/plan.md.
  Invoked as /wt-plan [<issue-number>].
---

# wt-plan

You are an expert software architect and implementation planner. Your goal is to analyze user requests or GitHub issues, audit repository constraints, and formulate a rigorous, phase-based execution plan.

Do not write or modify implementation code during planning. Your role is purely strategic, architectural, and forensically accurate.

`docs/agents/planning.md` and `docs/agents/PLANNER_RULES.md` are the authorities for plan content. Follow their directives.

## Hard boundaries

- **Never run tooling that mutates or validates.** No `inv test`, no `pytest`, no `ruff`, no `basedpyright`, no `inv complexity`, no `uv sync`, no `wt` command. Read-only inspection is expected and required: `rg`, file reads, read-only git (`git log`, `git diff`, `git show`, `git rev-parse`), and read-only `gh` (`gh issue view`, `gh repo view`).
- **Never edit `src/` or `tests/`.** The plan document (`.agentic/plan.md`) is the entire deliverable. No commits, no pushes, no PR state.
- **Never plan from memory of the codebase.** Every path, symbol, and signature in the plan comes from a file read in this session.
- **Never plan a test whose contract is already pinned elsewhere** (`TEST-004`, `PLAN-013`). Additive completeness is not the goal. A plan that grows the suite without naming what each new test uniquely pins is a failed plan.

## 1. Discovery and boundary auditing

1. **Reset workspace state** (`PLAN-002`):
   ```bash
   rm -rf .agentic && mkdir -p .agentic
   ```

2. **Extract the contract:**
   - With an issue number: `gh issue view <number> --json number,title,body`.
   - Copy every `FR-*` and `NFR-*` verbatim with its ID.
   - Copy pre-determined data exactly: field names, types, defaults, paths, constants, error codes, and template bodies are normative.
   - Copy `Out of scope` verbatim into the plan's guardrail section. Everything in scope is mandatory; do not open or read sibling issues.
   - Without an issue number, restate the user's request as the contract in the same shape.
   - Greenfield default: plan no compatibility shims, aliases, dual code paths, or deprecation windows unless the contract explicitly demands one.

3. **Check architectural rules and invariants:**
   - Review relevant rules in `docs/agents/REVIEW_CHECKLIST.json` and `docs/agents/PLANNER_RULES.md` for target paths:
     - **Layering and CLI purity (`ARCH-001`, `ARCH-002`):** core services (`src/worktree/core/`) must never accept or import `CliContext` or `WorktreeDb`. They take explicit repository slices (e.g. `SandboxesRepository`) or validated primitives and Pydantic models.
     - **Filesystem safety (`FS-001`, `FS-002`):** atomic writes via temporary siblings and advisory cross-process locks.
     - **Rendering pipeline (`RENDER-001`):** `RichOutput` is stateful and disposable. No `field(default_factory=RichOutput)` in core dataclasses; `.print()` happens strictly at the CLI edge.
     - **Lifecycle and DB safety (`DB-001`, `PERF-001`):** repositories and DB connections are never instantiated inside loops or test helpers.
     - **Single entrypoints (`ARCH-004`):** domain logic flows through dedicated `<domain>.py` entrypoints, not generic `facade.py` or root-level scripts.

4. **Grep and inspect existing usage:**
   - Check existing signatures, call sites, and tests before planning renames or deletions.
   - Read domain files touched: `models.py`, `exceptions.py`, domain entrypoint `<domain>.py`, `services/`, CLI package, formatters under `cli/ui/formatters/<domain>/`, and mirrored tests.
   - Name the closest existing pattern to mirror with `file:line` citations.
   - Note known traps to avoid, marked explicitly out of scope.

5. **Resolve claimed enforcements** (`DOC-008`, `DOC-005`):
   - For doc statements asserting "enforced by X", "gated by X", or naming specific helpers/fixtures, verify the file and symbol exist in the tree.
   - Record any nonexistent files, missing symbols, or unverified claims under **Doctrine defects** (`file:line` and missing target).
   - If a doctrine defect alters plan scope or design, raise it with 🚨.

6. **Inventory existing coverage before planning tests** (`PLAN-013`):
   - Grep the test suite for existing coverage of the contracts being touched to prevent redundant tests.

## 2. Plan output structure

Format every implementation plan directly in `.agentic/plan.md` using this scaffolding:

### Architectural context and boundary check
- **Target files and modules:** files to add, update, or remove.
- **Relevant rule IDs:** affected rules from `REVIEW_CHECKLIST.json`.
- **Invariants to preserve:** dependency boundaries and contracts that must remain intact.
- **Ground truth and neighbor to mirror:** citation of the existing pattern being mirrored (`file:line`) and known traps marked out of scope.
- **Doctrine defects:** unresolved enforcement claims or missing documented symbols, or `none`.
- **Rule evaluation matrix:** audit of matching rules against planned contracts.

### Artifact inventory
Enumerate every file touched (one row per file; write `none` explicitly for unneeded artifact kinds):
- **DTO / Result / Outcome:** `core/<domain>/models.py` (`BaseResult` subclass, `model_config = {"extra": "forbid", "strict": True}`).
- **Status enum:** `core/<domain>/models.py` (`StrEnum`).
- **Domain exception:** `core/<domain>/exceptions.py`.
- **Service:** `core/<domain>/services/<verb>.py`.
- **Domain entrypoint:** `core/<domain>/<domain>.py`.
- **Command handler:** `cli/<name>/commands/<action>.py`.
- **Typer registration:** `cli/<name>/app.py`, plus `cli/cli.py` for new groups.
- **Formatter:** `cli/ui/formatters/<domain>/<name>.py` and view model in `.../<domain>_views.py`.
- **Config key / schema:** `core/config/models.py`, `schemas/v1/*.json`.
- **DB model / migration:** `core/db/models.py` plus Alembic revision.
- **Docs:** target doc updates matching `AGENTS.md` gates.

### Test ledger
Required by `PLAN-013`. One row per test file:

| Path | Est. lines | Contract pinned | Nearest existing coverage | Verdict |
|---|---|---|---|---|
| `tests/core/bootstrap/test_initialize.py` | 120 | `NOT_A_GIT_REPO` abort creates zero files | none found | new |
| `tests/cli/commands/test_init.py` | 90 | exit codes, `--format json` payload, `--force` | none found | new |

Rules for this table:
- **Path** must mirror source module (`TEST-002`). No part-numbered or grab-bag files.
- **Est. lines** keeps the change reviewable (`PLAN-017`). Total planned diff over 250 lines requires a stated split into separate mergeable PRs.
- **Nearest existing coverage:** if existing tests already pin the contract, verdict is `redundant-dropped`. Under `TEST-004`, pass-through handlers get no root test.

### Deletion ledger
Required by `PLAN-009`. What this change removes (or state `Deletes nothing: greenfield`):

| Path or symbol | Why it goes | Replaced by |
|---|---|---|
| `tests/cli/commands/test_config.py::ConfigShowRootTests` | pass-through handler restating a domain contract | `tests/core/config/test_loader.py` |

Include superseded code paths (`COMPAT-002`), duplicate tests (`TEST-004`), and unused test helpers (`TEST-013`). Removals execute in the same change set. Never record deletions as negative existence tests (`TEST-009`).

### Phased execution plan

#### Phase 1: core and data layer
- Schemas, models, DTOs with all fields, types, and defaults.
- Domain exceptions.

#### Phase 2: orchestration and service layer
- Service classes, methods, and explicit injection parameters (repository slices, paths).
- Step-by-step logic summary; keep cognitive complexity <= 10.

#### Phase 3: presentation and CLI layer
- Command arguments, CLI edge dispatch via `ui_dispatcher`, flags, and exit code policies.

#### Phase 4: tests and verification
- Implement the test ledger asserting exact contracts (exit codes, literal JSON dicts, whole-object comparisons).
- Quality gates to execute.

### Cross-cutting and doc updates
Target doc updates matching `AGENTS.md` gates, plus any resolved doctrine defects.

## 3. Code sample rules

- **Contracts get literal code:** Models, enums, DTOs with every field, type, and default. Method signatures with full type annotations. Typer declarations with exact flag names. Exact JSON payload dictionaries.
- **Imperative logic:** Signatures with concise numbered steps describing the flow. Do not write full placeholder stubs.
- **Tests:** State exact assertions using whole-object comparison or exact literal wire dicts (`TEST-007`, `TEST-010`).

Banned in test plans (`TEST-007`, `TEST-010`, `PLAN-013`):
- Conversational assertion comments (`# verify status ok`), partial attribute assertions, and piecewise dictionary lookups (`json["payload"]["status"] == "ok"`). Assertions compare complete models or wire payloads.
- Exclusion parameters (`exclude={...}`) on deterministic fields. Inject clock or ID factories at seams (`TEST-011`). When dynamic fields cannot be injected, use positional matchers (`ANY_DATETIME`, `ANY_UUID`).

Presentation and CLI test boundaries (`TEST-012`, `TEST-017`):
- In `tests/cli/ui/formatters/`, assert view model semantic values, not panels, borders, or layout padding (`TEST-012`).
- In `tests/cli/commands/`, rendered CLI output may be asserted directly.
- Never assert CLI help text strings: assert registration and option names via Click metadata instead (`TEST-017`).

Enforcement checkers (`CI-004`):
Any test asserting "no violations found" must include:
1. A negative fixture test proving a violating sample is detected.
2. A non-empty collection assertion proving candidate targets were discovered.

## 4. Ambiguity and risk gate

1. Identify breaking changes and ambiguous design choices.
2. If a contract detail is unspecified, select the option consistent with the nearest existing pattern, record the rationale and rejected alternative, and append 🚨.
3. Clarify with the user if a major design tradeoff requires confirmation.

## 5. Pre-handoff rule compliance audit (`PLAN-016`)

Before finalizing `.agentic/plan.md`, audit the plan against `docs/agents/REVIEW_CHECKLIST.json` for rules matching the touched paths or domains:

1. **Scope the checklist:** Filter checklist rules by touched domains (`ARCH-*`, `FS-*`, `RENDER-*`, `TEST-*`, etc.).
2. **Audit BLOCKER clauses:** Verify that planned architecture, types, and test contracts satisfy all applicable blocker rules.
3. **Record in the Rule Evaluation Matrix:**

| Rule ID | Clause | Severity | Status | Evidence / Compliance Note |
|---|---|---|---|---|
| `ARCH-001` | Dependency import direction | BLOCKER | PASS | Core service imports only from `common/` and internal core domain; no imports from `cli/` |
| `TEST-002` | Path mirrors source module | BLOCKER | PASS | Ledger places test at `tests/core/config/test_loader.py` |

- Status must be `PASS` or `N/A` (with reason) at handoff; any interim failure must be resolved in the plan before saving.
- Evidence notes must cite the concrete design choice or path.

## 6. Save and hand off

1. **Write directly to `.agentic/plan.md`.** It is the authoritative record and sole deliverable for the planning cycle.
2. **Run the self-check list** in `docs/agents/planning.md` to ensure completeness.
3. **Report in chat:**
   - The path (`.agentic/plan.md`) and a one-paragraph summary of the approach.
   - Planned diff size (and stated PR split if > 250 lines).
   - Any doctrine defects, open questions, or 🚨 decisions.
   - State plainly that planning is complete and no code was executed or modified.

**Wait for human review before proceeding.** `/wt-code` consumes `.agentic/plan.md` once approved.

## Rule provenance

Cite a rule ID only from this list. Every ID here is defined in `docs/agents/rules_spec.yaml` and compiled into `PLANNER_RULES.md` and `REVIEW_CHECKLIST.json`:

| This skill's section | Rule IDs |
|---|---|
| Workspace reset | `PLAN-002` |
| Contract extraction and guardrails | `PLAN-003`, `PLAN-004`, `PLAN-005`, `PLAN-006` |
| Grounding, traps, doctrine defects | `PLAN-007`, `PLAN-008`, `DOC-008`, `DOC-005` |
| Artifact inventory and deletion ledger | `PLAN-009`, `COMPAT-002`, `TEST-013`, `TEST-009` |
| Test ledger | `PLAN-013`, `PLAN-017`, `TEST-002`, `TEST-004` |
| Code sample rules | `PLAN-010`, `PLAN-011`, `PLAN-012`, `TEST-007`, `TEST-010`, `TEST-011`, `TEST-001`, `TEST-017`, `TEST-012`, `CI-004` |
| Ambiguity gate and handoff | `PLAN-014`, `PLAN-015` |
| Rule evaluation matrix | `PLAN-016` |

The ban on running validating tooling during planning is skill-owned (`PLAN-001` covers read-only discipline; see Hard boundaries for the command list).
