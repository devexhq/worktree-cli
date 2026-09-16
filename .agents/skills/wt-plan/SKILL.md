---
name: wt-plan
description: >-
  Formulate a phased, invariant-safe implementation plan for a worktree-cli change
  before executing code changes. Audits repository constraints against REVIEW_CHECKLIST.json,
  grounds artifacts in the tree, declares a test ledger with markers and line budgets,
  declares what the change deletes, writes the full plan to .agentic/master-plan.md, and
  derives a condensed coding-focused .agentic/plan.md from it. Invoked as /wt-plan [<issue-number>].
---

# wt-plan

You are an expert software architect and implementation planner. Your goal is to analyze user requests or GitHub issues, audit repository constraints, and formulate a rigorous, phase-based execution plan.

Do not write or modify implementation code during planning. Your role is purely strategic, architectural, and forensically accurate.

`docs/agents/planning.md` and `docs/agents/PLANNER_RULES.md` are the authorities for plan content. Follow their directives.

## Hard boundaries

- **Never run tooling that mutates or validates.** No `inv test`, no `pytest`, no `ruff`, no `basedpyright`, no `inv complexity`, no `uv sync`, no `wt` command. Read-only inspection is expected and required: `rg`, file reads, read-only git (`git log`, `git diff`, `git show`, `git rev-parse`), and read-only `gh` (`gh issue view`, `gh repo view`).
- **Never edit `src/` or `tests/`.** The plan documents (`.agentic/master-plan.md` and `.agentic/plan.md`) are the entire deliverable. No commits, no pushes, no PR state.
- **Never plan from memory of the codebase.** Every path, symbol, and signature in the plan comes from a file you read in this session.
- **Never plan a test whose contract is already pinned elsewhere** (`TEST-004`, `PLAN-013`). Additive completeness is not the goal. A plan that grows the suite without naming what each new test uniquely pins is a failed plan.

## 1. Discovery and boundary auditing

1. **Reset workspace state** (`PLAN-002`). Clear the previous cycle's artifacts so a stale review, plan, or master plan can never be read as current. `-rf` matters: `.agentic` is a directory, so `rm -f` exits non-zero and short-circuits the chained `mkdir`, leaving every stale artifact in place while looking like a reset.
   ```bash
   rm -rf .agentic && mkdir -p .agentic
   ```

2. **Extract the contract.**
   - With an issue number: `gh issue view <number> --json number,title,body`.
   - Copy every `FR-*` and `NFR-*` verbatim with its ID. Paraphrase drops clauses.
   - Copy pre-determined data exactly: field names, types, defaults, paths, constants, error codes, and template bodies are normative.
   - Copy `Out of scope` verbatim into the plan's guardrail section. Everything in scope is mandatory; do not open or read sibling issues.
   - Without an issue number, restate the user's request as the contract in the same shape, noting that it is a restatement.
   - Greenfield default: plan no compatibility shims, aliases, dual code paths, or deprecation windows unless the contract explicitly demands one.

3. **Check architectural rules and invariants.**
   - Load `docs/agents/REVIEW_CHECKLIST.json` and `docs/agents/PLANNER_RULES.md`. Filter checklist rules against the target paths and packages touched by the change.
   - Strictly verify:
     - **Layering and CLI purity (`ARCH-001`, `ARCH-002`):** core services (`src/worktree/core/`) must never accept or import `CliContext` or `WorktreeDb`. They take explicit repository slices (for example `SandboxesRepository`) or validated primitives and Pydantic models.
     - **Filesystem safety (`FS-001`, `FS-002`):** atomic writes via temporary siblings and advisory cross-process locks.
     - **Rendering pipeline (`RENDER-001`):** `RichOutput` is stateful and disposable. No `field(default_factory=RichOutput)` in core dataclasses; `.print()` happens strictly at the CLI edge.
     - **Lifecycle and DB safety (`DB-001`, `PERF-001`):** repositories and DB connections are never instantiated inside loops or test helpers.
     - **Single entrypoints (`ARCH-004`):** domain logic flows through dedicated `<domain>.py` entrypoints, not sprawling facades or root-level scripts.

4. **Grep and inspect existing usage.**
   - Check existing signatures, call sites, and tests before planning renames or deletions.
   - Read the domain docs the change touches, then read what exists today in every domain it touches: `models.py`, `exceptions.py`, the domain entrypoint `<domain>.py`, `services/`, the CLI package, formatters under `cli/ui/formatters/<domain>/`, and mirrored tests.
   - Name the closest existing implementation you will mirror with `file:line` citations and follow it end to end.
   - Record a ground-truth table (surface, `file:line`, what exists today), the pattern to mirror, and every trap a lower-context implementer could fall into, each marked explicitly out of scope.

5. **Resolve every claimed enforcement** (`DOC-008`, `DOC-005`). Docs and rules in this repo assert that things are enforced. Before relying on any such claim, resolve it to a file that exists.
   - For each doc sentence of the form "enforced by X", "gated by X", or "see X", confirm X exists (`rg --files -g '<name>'` or a direct read). Claims naming a test module, hook, workflow step, or proposal document are the ones that rot.
   - For each helper, fixture, builder, or harness symbol a doc tells you to use, confirm the symbol exists in the tree.
   - Check the rule examples too. A compiled rule can cite a nonexistent module in its own `positive_example`, which makes the exemplar teach the defect it forbids.
   - Record each unresolved claim in the plan under **Doctrine defects** with the doc line and what is missing. An unresolved enforcement claim is a finding, not a detail: it means a rule you are about to plan against is checked by nothing.
   - If a doctrine defect changes the shape of the plan, stop and raise it with 🚨 rather than quietly planning around it.

6. **Inventory existing coverage before planning any test** (`PLAN-013`). For every contract the change touches, grep the suite for a test that already pins it. You cannot judge whether a new test earns its place without this.

## 2. Plan output structure

Format every implementation plan in `.agentic/master-plan.md` using this exact scaffolding.

### Architectural context and boundary check
- **Target files and modules:** files to add, update, or remove.
- **Relevant rule IDs:** affected rules from `REVIEW_CHECKLIST.json`.
- **Invariants to preserve:** dependency boundaries and contracts that must remain intact.
- **Ground truth and neighbor to mirror:** citation of the existing pattern being mirrored (`file:line`) and known traps marked out of scope.
- **Doctrine defects:** unresolved enforcement claims and missing documented symbols found in step 1.5, or `none`.
- **Rule evaluation matrix:** see section 5 for the evidence rules this table must satisfy.

### Artifact inventory
Enumerate every file you will touch (one row per file; write `none` explicitly for artifact kinds the change does not need):
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
Required by `PLAN-013`. Tests get their own table, because path, marker, and budget are executable facts that a prose tier label does not carry. One row per test file:

| Path | Marker | Est. lines | Contract pinned | Nearest existing coverage | Verdict |
|---|---|---|---|---|---|
| `tests/core/bootstrap/test_initialize.py` | `integration` | 120 | `NOT_A_GIT_REPO` abort creates zero files | none found | new |
| `tests/cli/commands/test_init.py` | `cli` | 90 | exit codes, `--format json` payload, `--force` | none found | new |

Rules for this table:
- **Path** must satisfy the parity mappings in `TEST-002`, including the CLI command collapse. No part-numbered or grab-bag files.
- **Marker** is the executable tier: one primary marker per module (`unit`, `integration`, `cli`, `invariant`), `slow` only as an addition, chosen by real cost as a labeling convention — `TEST-016`'s BLOCKER cardinality requirement was reversed by ADR-0002. Choose by real cost, not by narrative: reading and writing under `tmp_path` is `unit`; subprocess git, on-disk SQLite, and cross-process locks are `integration`. When a module must mix tiers, say so and declare markers per class so each tier stays selectable.
- **Est. lines** keeps the change reviewable, per `PLAN-017`. A total planned diff over 250 lines requires a stated split into separately mergeable PRs.
- **Nearest existing coverage** is the output of step 1.6. If an existing test already pins the contract, the verdict is `redundant-dropped` and the row stays in the table as the record of that decision. Under `TEST-004`, a pass-through handler gets no root test, and no row may restate a contract already asserted under `tests/core/` for the same result type.

### Deletion ledger
Required by `PLAN-009`. What this change removes. A change that only adds is either greenfield or under-planned, so state `Deletes nothing: greenfield` explicitly when that is the answer:

| Path or symbol | Why it goes | Replaced by |
|---|---|---|
| `tests/cli/commands/test_config.py::ConfigShowRootTests` | pass-through handler restating a domain contract | `tests/core/config/test_loader.py` |

Include superseded code paths (`COMPAT-002`), tests that duplicate a contract (`TEST-004`), and any harness symbol whose only caller would be its own verification test (`TEST-013`). Removals are executed in the same change set as the code that supersedes them, and never recorded as a negative existence test (`TEST-009`).

### Phased execution plan

#### Phase 1: core and data layer (inner domain)
- Schema updates, migrations, base repository refactors.
- Explicit input and output types, preferring Pydantic models or primitives over raw dicts.
- Literal code for DTOs and models with all fields, types, and defaults.

#### Phase 2: orchestration and service layer
- Service classes and method signatures, with repository slices, paths, and dependencies as required injection parameters.
- Signatures with Google-style docstrings and numbered pseudo-code stubs ending in `raise NotImplementedError`.
- Keep cognitive complexity at or under 10 by decomposing into named helpers in the plan.

#### Phase 3: presentation and CLI layer (outer edge)
- Command arguments, context extraction from `CliContext`, orchestrator flow.
- Terminal output routes through the dispatcher strictly at the CLI edge.
- Exact Typer flags, arguments, and help copy.

#### Phase 4: tests and verification
- Implement the test ledger. Do not introduce a test file the ledger does not list.
- State the exact contract each test asserts: exit codes, exact dicts, whole-object comparison.
- Name the gate commands the implementer will run.

### Cross-cutting and doc updates
Doc updates that match `AGENTS.md` gates, plus any doctrine defect this change is fixing.

## 3. Code sample rules

- **Contracts get literal, final code.** Models and enums with every field, type, and default. Full signatures with type hints and Google-style docstrings. Typer declarations with exact flag names and help copy. Formatter class shells. Exact JSON payload dicts. Exact error, warning, and fix strings.
- **Production imperative bodies get a stub.** Real signature, real docstring, body as numbered steps in comments, ending in `raise NotImplementedError`. A plan with finished code cannot be reviewed as a plan.
- **Test bodies get setup outline plus literal whole-object assertions.** Real signature, docstring, setup as numbered comments, and literal whole-object assertion calls, ending in `raise NotImplementedError`.

Banned in test stubs and tables, by form (`TEST-007`, `TEST-010`, `PLAN-013`):
- Conversational assertion comments (`# verify status ok`), subset assertions on the result under test, and piecewise dictionary lookups (`json["payload"]["status"] == "ok"`). The expected object names every field, or the wire payload is an exact literal dict.
- Any waiver expressed outside the comparison. There is no `exclude` parameter: a field the test declines to state is stated as a matcher at its own position (`ANY_DATETIME`, `ANY_UUID`, `ANY_GIT_SHA`), which still pins its type or shape. Plan the seam first, though: if a timestamp or generated id reaches a result field, inject the clock or id factory per `TEST-011` so the plan can specify a literal and needs no matcher at all. An expected object carrying a matcher is built with `model_construct`, because the plain constructor rejects one under `strict=True`.
- Note which of these the plan is most likely to get wrong. `exclude={"errors"}` was forbidden by name in two compiled BLOCKER rules and shipped anyway, so a waived field is the clause to audit hardest.

Banned in test stubs, by target (`TEST-001`, `TEST-017`, `TEST-012`):
- **Formatter render assertions stay semantic-value-only** (`TEST-012`). In `tests/cli/ui/formatters/`, never plan an assertion against a panel title, status label, field caption, prose sentence, glyph, or padding — the render assertion checks a value carried by the view model. CLI runner tests under `tests/cli/commands/` are different: ADR-0002 reversed D2/`TEST-017`, so they may assert real rendered output directly, including labels and prose, ideally pinned via snapshot testing.
- **Help text wording** (`TEST-017`). Still banned everywhere: assert command registration and option names through Click metadata instead.

Enforcement code has one extra requirement, from `CI-004`. Any test whose assertion is "no violations were found" must be planned together with two companions, because an empty result set passes that assertion trivially:
1. A negative fixture test that constructs a violating sample and asserts the checker flags it. The fixture must have the same shape as the real code it polices; a checker for class-based tests proven only against a module-level function is unproven.
2. A non-empty collection assertion, so a scanner that silently collects nothing cannot report success.

```python
class MarkerTaxonomyTests:
    def test_every_test_module_declares_one_primary_marker(self) -> None:
        # 1. Collect tests/**/test_*.py and assert the collection is non-empty
        # 2. Parse each module's pytestmark
        # 3. Fail naming modules with zero or multiple primary markers
        raise NotImplementedError

    def test_checker_flags_a_module_with_no_marker(self) -> None:
        # Negative fixture: an unmarked module written to tmp_path must be flagged
        raise NotImplementedError
```

## 4. Ambiguity and risk gate

1. Identify potential breaking changes and ambiguous design choices.
2. If the contract leaves a detail genuinely unspecified, choose the option consistent with the nearest existing pattern, record the choice and the rejected alternative, and append 🚨 to that line.
3. Ask the user one clarifying question if a design tradeoff needs confirmation before execution begins.

## 5. Pre-handoff rule compliance audit (`PLAN-016`)

Before writing `.agentic/master-plan.md`, sweep the checklist item by item.

1. **Scope the checklist.** Load `docs/agents/REVIEW_CHECKLIST.json` and filter for rules whose `scope` matches touched files or package domains.
2. **Decompose multi-clause rules.** A rule with several independent clauses gets one matrix row per clause. `TEST-007`, for example, carries four: every field of the result under test asserted, no waiver outside the comparison, no field left to its default, and a matcher only where the seam could not be injected. A single row for a four-clause rule hides three of them.
3. **Audit each clause against the draft plan** using the rule's `evaluation_criteria`.
4. **Enforce the blocker gate.** If any `BLOCKER` clause is violated, refactor the plan before saving.

### Evidence rules for the matrix

A row is not filled until it carries evidence a reader can check without trusting you.

- **`FAIL` is a real status and an expected interim one.** Status is `PASS`, `FAIL`, or `N/A`, and every `FAIL` is resolved in the plan before saving, so the saved matrix carries none. An audit whose only outcomes are pass and not-applicable audits nothing, and that is how a plan carries a complete matrix and still breaches a `BLOCKER`.
- **Evidence quotes the plan.** Give the section or stub and the literal line the verdict rests on.
- **Restating the rule is not evidence.** Banned evidence phrases: "follows the pattern", "complies", "uses `assert_model_equal`", "tests are contract-based", and any sentence that would read identically before the plan was written.
- **`N/A` names why the scope does not match**, for example "no formatter in this change".
- **Write the adversarial sentence.** For every `BLOCKER` clause, write the one sentence a reviewer would use to fail this plan, then either fix the plan or record why the sentence does not hold. A self-audit with no adversarial step approves itself.

Shape, shown with a failing row because a failing exemplar is the one worth copying:

| Rule ID | Clause | Severity | Status | Evidence (quoted) |
|---|---|---|---|---|
| `TEST-007` | no waiver outside the comparison | SUGGESTION | FAIL | Phase 4 stub writes `assert_model_equal(result, expected, exclude={"errors"})`; rewritten to name `errors` per parameter case before saving |
| `TEST-002` | path mirrors source module | BLOCKER | PASS | Ledger row 3 is `tests/cli/ui/formatters/status/test_status.py` for `cli/ui/formatters/status/status.py` |

## 6. Save and hand off

1. **Write the full plan to `.agentic/master-plan.md`.** This is the authoritative record and contains all sections, including the rule evaluation matrix, the test and deletion ledgers, doctrine defects, and self-check results.
2. **Run the self-check list** at the end of `docs/agents/planning.md` and verify the matrix has zero FAIL rows.
3. **Derive `.agentic/plan.md`** from the master plan by omitting only the rule evaluation matrix and the self-check verification section. Everything else, including both ledgers and the doctrine defects, is retained verbatim: the implementer needs the markers, the budgets, and the deletions. The condensed file must stand on its own, with no broken headings or dangling references.
4. Report:
   - Both paths and a one-paragraph summary of the approach.
   - The planned diff size and, if over 250 lines, the split.
   - Every doctrine defect, open question, and 🚨 decision restated in chat.
   - Plainly, that this was planning only: nothing was implemented, tested, committed, or pushed.

**A human reviews the plan before implementation.** Do not offer to start implementing in the same breath; stop and wait. `/wt-code` is what consumes the approved plan.

## Rule provenance

Cite a rule ID only from this list. Every ID here is defined in `docs/agents/rules_spec.yaml` and compiled into `PLANNER_RULES.md` and `REVIEW_CHECKLIST.json`, so a citation resolves to a rule a reviewer can read. Never invent an ID for a requirement that has no rule behind it.

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

Two requirements in this skill are skill-owned and have no compiled rule, so state them as this skill's directive rather than citing an ID: the ban on running validating tooling during planning (`PLAN-001` covers read-only discipline but not the command list), and the derivation of `.agentic/plan.md` from `.agentic/master-plan.md`.
