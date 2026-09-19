# Planning Before Implementation

Read this **before writing any code** for a GitHub issue. The plan document (`.agentic/plan.md`) is the deliverable.

While planning, remain **read-only**: do not edit `src/` or `tests/`, do not run `inv test`, do not commit, push, or touch PR state.

## When to plan

Plan when an issue adds or changes: a command or subcommand, a DTO/`*Result` model, a status enum, a domain exception, a service, a facade method, a formatter, a config key, a JSON/YAML schema field, or a `core/db/` table.

Skip planning only for a single-file, no-new-surface change (a typo, a message string, a one-line branch fix).

---

## Step 1: Extract the contract from the issue

```bash
gh issue view <number> --json number,title,body
```

Extract the contract directly from the issue body (see [github-issues.md](github-issues.md); PLAN-003 through PLAN-006):

- Copy every `FR-*`/`NFR-*` verbatim with its ID, plus **Pre-determined data**, **Out of scope**, and **Definition of Done** verbatim. No paraphrasing, no "Goal" or "As a user" prose.
- Do not open or consult sibling issues.
- Plan zero backwards-compatibility shims, aliases, dual code paths, or deprecation windows unless the issue explicitly demands them.

If a detail is unspecified, choose the option matching the nearest existing pattern from Step 2, record the choice and rejected alternative in `### Decisions`, and append `🚨`.

---

## Step 2: Ground yourself in the current code

Read the codebase directly before planning; never plan from memory (PLAN-007, PLAN-008):

1. Read the always-on docs listed in [AGENTS.md](../../AGENTS.md).
2. Read the existing code for every domain touched: `core/<domain>/{models,exceptions,facade}.py`, `services/`, `cli/<name>/app.py` and `commands/`, `cli/ui/formatters/<domain>/`, and mirrored tests.
3. **Name the closest existing implementation to mirror**, with `file:line` citations (e.g. `wt config set` -> `Config.set` in `src/worktree/core/config/mutate.py` -> `ConfigSetResult` -> `config_set_command` -> `ConfigSetFormatter`). Quote a mirrored symbol as signature + docstring only, never its body.
4. **Verify doc field lists against source code**; record stale doc claims as traps.
5. If the issue's description of current state differs from the codebase, state the discrepancy and the corrected state.
6. **Name every trap**: dead code, lookalike symbols, duplicate implementations, stale docs. Mark each out of scope. (Use `/wt-test-planner` Steps 1b-1d to audit dead status values and existing coverage.)

Record findings as a ground-truth table (`Surface`, `Location`, `What exists`), one clause per cell, `file:line` citations, no narrative. **Pattern to mirror** and **Traps** live exclusively here — do not repeat them in Instructions, Decisions, or Edge cases.

---

## Step 3: Enumerate every artifact

Produce an inventory with one row per file touched (exact path, exact identifier; no "e.g." or "etc."):

| Artifact | Kind | Path | New or changed | Requirement |
|---|---|---|---|---|
| `SandboxPruneResult` | DTO | `src/worktree/core/sandbox/models.py` | new | FR-2 |

State **"none"** for each kind the issue does not need. Path per kind:

- **DTO / Result / Outcome / Status enum** -> `core/<domain>/models.py`
- **Domain exception** -> `core/<domain>/exceptions.py`
- **Service** -> `core/<domain>/services/<verb>.py` (public models never live here)
- **Facade method** -> `core/<domain>/facade.py`
- **Command handler** -> `cli/<name>/commands/<action>.py`
- **Typer registration** -> `cli/<name>/app.py` (and `cli/cli.py` for new top-level groups)
- **Formatter** -> `cli/ui/formatters/<domain>/<name>.py`; view models in `<domain>_views.py` or `<name>_view.py`; register in `register_<domain>_formatters` and `__all__`
- **Config key** -> `core/config/models.py` + `schemas/v1/config.json` + defaults generator
- **JSON / YAML schema** -> `src/worktree/schemas/v1/*.json`
- **DB model or migration** -> `core/db/models.py` + Alembic migration
- **Tests** -> mirrored `tests/` path, tier named (see `docs/agents/testing.md#the-four-execution-tiers`)
- **Docs** -> only docs matching AGENTS.md gates (`docs/cli/`, `schemas.md`, `architecture.md`, `README.md`)

Decompose every planned function so it stays below cognitive complexity <= 10 (PLAN-012).

---

## Step 4: Write the plan

Structure each FR (or testable group of FRs) under these subheadings:
1. `> <verbatim requirement text>`
2. `### Instructions`
3. `### Code`
4. `### Decisions`
5. `### Edge cases`
6. `### Tests`

> [!TIP]
> Run `/wt-test-planner --plan` to generate the `### Tests` table and stubs.

### Instructions: Imperative verbs only

Strictly imperative verbs ("Create `...`", "Assert `...`"). State what to do, not why — rationale goes in `### Decisions`. Do not repeat what code samples or test tables already show.

### Code sample rules

**Literal contracts:** write exact code for anything that is a contract — model/enum definitions with every field and default, full signatures with type hints and docstrings, Typer flags and help text, formatter shells, literal JSON dicts, error/warning strings, fixtures, regex patterns (PLAN-010).

```python
class SandboxPruneStatus(StrEnum):
    """Outcome states for a sandbox prune operation."""

    OK = "ok"
    NOTHING_TO_PRUNE = "nothing_to_prune"
    FAILED = "failed"


class SandboxPruneResult(BaseResult):
    """Result of pruning stale sandboxes and orphaned directories."""

    model_config = {"extra": "forbid", "strict": True}

    status: SandboxPruneStatus
    pruned_items: list[str] = []
```

**Production stubs:** exact signature + one-line intent docstring + `raise NotImplementedError`. No numbered steps, no body code (PLAN-011).

```python
def prune_sandboxes(context: CliContext, dry_run: bool = False) -> SandboxPruneResult:
    """Delete stale sandbox records, orphaned directories, and temporary branches."""
    raise NotImplementedError
```

**Test stubs:** signature + single-line docstring starting `[<tier>/<type>]` (per `docs/agents/testing.md#the-four-execution-tiers`), naming the public symbol exercised and the exact outcome contract, ending `raise NotImplementedError` (PLAN-018). The `### Tests` table indexes them (`Test`, `Tier`, `Outcome`); the docstring holds the exact assertion contract.

```python
class SandboxPruneCliIntegrationTests:
    def test_prune_empty_returns_nothing_to_prune(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        """[tier-3/integration] wt sandbox prune: empty sandboxes directory prints 'Nothing to prune'; exit 0."""
        raise NotImplementedError
```

Use absolute `worktree.*` imports at module top level and reference only symbols verified in Step 2.

### Decisions: The sole home for rationale

Format: `- **<decision point>:** <choice>, because <one clause>. Rejected: <alternative>. [🚨]`. Append `🚨` when a decision needs confirmation.

### Edge cases: Genuine implementation gotchas only

Non-obvious traps, execution gotchas, or sequencing constraints not already in Ground truth Traps or Decisions. Do not restate standard branch logic.

### Tests: Summary index table and contract stubs

A concise index table paired with the stubs from Code sample rules:

| Test | Tier | Outcome |
|---|---|---|
| `SandboxPruneCliIntegrationTests::test_prune_empty_returns_nothing_to_prune` | Tier 3 (integration) | exit 0; "Nothing to prune" |

Assert exact contracts (literal JSON dict, exit code, filesystem state, or `*Result` fields). Ban vague phrasing (`"Verifies pruning works"`), piecewise assertions (`"Checks exit code is 0"`), and omitted fields.

### Plan document template

````markdown
# Issue #<n>: <title>

Planning only. Grounded against `<base branch>` at `<short sha>`.

## Contract

<Verbatim FR-*/NFR-* list with IDs. Pre-determined data reproduced exactly.>

**Out of scope:**
- ...

**Pre-determined data:**
- ...

**Definition of Done:**
- [ ] ...

---

## Ground truth

| Surface | Location | What exists |
|---|---|---|
| <surface> | `path:line` | <one clause> |

**Pattern to mirror:** <domain path chain, with citations; reproduced symbols shown as signature + docstring only>

**Traps (explicitly not touched):**
- <dead code, lookalike symbol, stale doc>

---

## Artifact inventory

| Artifact | Kind | Path | New or changed | Requirement |
|---|---|---|---|---|

Not needed: <kinds from the Step 3 checklist that are "none">

## Deletion ledger

<Deletion table or 'Deletes nothing: greenfield.'>

---

## FR-<n>: <name>

> <verbatim requirement text>

### Instructions

1. <imperative action: exact file, exact symbol, exact change; no inline rationale>

### Code

<literal contracts, fixtures, constants; production stubs as signature + one-line intent docstring + raise NotImplementedError>

### Decisions

- **<decision point>:** <choice>, because <one clause>. Rejected: <alternative>. <🚨 if a reviewer should confirm this.>

### Edge cases

- <genuine implementation gotcha not in Traps or Decisions>

### Tests

| Test | Tier | Outcome |
|---|---|---|
| `<TestClass>::<test_method>` | Tier <n> (<type>) | <summary exit code or status> |

```python
class <TestClass>:
    def <test_method>(self, ...):
        """[<tier>/<type>] <public_symbol>: <exact outcome contract>."""
        raise NotImplementedError
```

---

## Cross-cutting

- **Docs gates that fire:** <specific docs, or "none" with the reason>
- **Validation:** `uv run inv test`, `uv run ruff format .`, `uv run ruff check .`, `uv run basedpyright src tests --level error`, `inv complexity --paths <files> --plain --failed`
- **Open questions:** <blocking ambiguities, each flagged 🚨, or "none">
````

---

## Step 5: Save and hand off

1. Verify the plan against `docs/agents/REVIEW_CHECKLIST.json` and `docs/agents/PLANNER_RULES.md` for every rule matching touched paths or domains, ensuring zero BLOCKER violations. Reread the plan's actual paths, imports, and stubs against each clause — do not just restate the rule. No compliance table in the plan.
2. Write the plan to `.agentic/plan.md` (overwriting any previous plan and deleting `.agentic/review.md`).
3. Report the plan path and state that planning is complete (no code implemented, tested, committed, or pushed). Restate every `🚨` decision and open question in the handoff message.
