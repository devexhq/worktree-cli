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

Extract the contract directly from the issue body (see [github-issues.md](github-issues.md)):

- Copy every `FR-*` and `NFR-*` verbatim with its ID. Do not paraphrase.
- Do not add "Goal" prose paragraphs or "As a user" narratives.
- Copy **Pre-determined data** exactly (field names, types, defaults, file paths, constants, error codes, templates).
- Copy **Out of scope** verbatim into the guardrails section.
- Copy any **Definition of Done** checklist verbatim.
- Do not open or consult sibling issues.
- Plan no backwards compatibility shims, aliases, dual code paths, or deprecation windows unless the issue explicitly demands them. Replace superseded paths directly.

If a detail is unspecified, choose the option matching the nearest existing pattern from Step 2, record the choice and rejected alternative in `### Decisions`, and append `🚨`.

---

## Step 2: Ground yourself in the current code

Read the codebase directly before planning:

1. Read the always-on docs listed in [AGENTS.md](../../AGENTS.md) (architecture, code-conventions, schemas, glossary, testing).
2. Read the existing code for every domain touched:
   - `src/worktree/core/<domain>/models.py`, `exceptions.py`, `facade.py`, `services/`
   - `src/worktree/cli/<name>/app.py` and `src/worktree/cli/<name>/commands/`
   - `src/worktree/cli/ui/formatters/<domain>/`
   - Mirrored tests under `tests/`
3. **Name the closest existing implementation to mirror**, with `file:line` citations (e.g. `wt config set` -> `Config.set` in `src/worktree/core/config/mutate.py` -> `ConfigSetResult` -> `config_set_command` -> `ConfigSetFormatter`). When quoting a mirrored symbol for reference, quote only its signature and docstring.
4. **Verify doc field lists against source code.** Record any stale doc claims as traps.
5. If the issue's description of current state differs from the codebase, state the discrepancy and the corrected state in the plan.
6. **Name every trap**: dead code, lookalike symbols, duplicate implementations, stale docs. Mark each out of scope. (Use `/wt-test-planner` Steps 1b–1d to audit dead status values and existing coverage).

Record findings in the plan as a ground-truth table (`Surface`, `Location`, `What exists`):

- **One clause per cell, max.** Use `file:line` citations; do not write narrative explanations inside cells.
- **Single ownership:** "**Pattern to mirror**" and "**Traps (explicitly not touched)**" live exclusively in Ground truth — do not repeat them in Instructions, Decisions, or Edge cases.

---

## Step 3: Enumerate every artifact

Produce an inventory with one row per file touched (exact path, exact identifier; no "e.g." or "etc."):

| Artifact | Kind | Path | New or changed | Requirement |
|---|---|---|---|---|
| `SandboxPruneResult` | DTO | `src/worktree/core/sandbox/models.py` | new | FR-2 |

State **"none"** for each kind the issue does not need:

- **DTO / Result / Outcome** -> `core/<domain>/models.py`. Subclasses `BaseResult`, carries a `status` `StrEnum`, sets `model_config = {"extra": "forbid", "strict": True}`. Operations that can fail return a result, not raise.
- **Status enum** -> same `models.py`. Every value must be reachable and covered by a test.
- **Domain exception** -> `core/<domain>/exceptions.py`, subclassing domain or `Definition*` base.
- **Service** -> `core/<domain>/services/<verb>.py` for imperative operations. Public models never live in `services/`.
- **Facade method** -> `core/<domain>/facade.py`, the domain's only public entry point.
- **Command handler** -> `cli/<name>/commands/<action>.py`: takes `CliContext`, returns core `*Result`, calls `ui_dispatcher.dispatch(result, output_format=output_format)`. No `print`, `rich` import, or `typer.echo` outside `cli/ui/`.
- **Typer registration** -> `cli/<name>/app.py` (and `cli/cli.py` for new top-level groups). Exact flag names, help text, `raise typer.Exit(code=1)` when `not result.ok`.
- **Formatter** -> `cli/ui/formatters/<domain>/<name>.py`, one `*Formatter` class implementing `transform` and `to_rich`. Inherit `to_json_serializable` without overriding. Presentation view models live in `cli/ui/formatters/<domain>/<domain>_views.py` (or `<name>_view.py`). Register in `register_<domain>_formatters` and `__all__` in `__init__.py`.
- **Config key** -> `core/config/models.py` plus `schemas/v1/config.json` plus defaults generator, stating default value.
- **JSON / YAML schema** -> `src/worktree/schemas/v1/*.json`, keeping `additionalProperties: false`.
- **DB model or migration** -> `core/db/models.py` plus Alembic migration.
- **Tests** -> Mirrored path under `tests/` with tier named: Tier 1 domain behavior, Tier 2 presentation contracts (transform equality, JSON wire format, view-derived Rich values), Tier 3 CLI wiring (`*RootTests` and `*CliIntegrationTests`), Tier 4 `tests/lint/` invariants.
- **Docs** -> Update only docs matching AGENTS.md gates (`docs/cli/`, `schemas.md`, `architecture.md`, `README.md`).

Ensure every planned function decomposes below cognitive complexity <= 10.

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

- Write instructions using strictly imperative verbs ("Create `...`", "Assert `...`").
- State what to do, not why. Put all rationale into `### Decisions`.
- Do not repeat details shown in code samples or test tables.

### Code sample rules

**Literal contracts:**
Write exact code for all contracts: model/enum definitions with every field and default, function signatures with full type hints and Google-style docstrings, Typer argument/option declarations with exact flag names and help text, formatter class shells, literal JSON wire dicts, error/warning strings, non-obvious fixtures, and regex patterns.

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

**Production stubs:**
Write the exact signature plus a one-line intent docstring, ending with `raise NotImplementedError`. Do not include numbered steps or body code.

```python
def prune_sandboxes(context: CliContext, dry_run: bool = False) -> SandboxPruneResult:
    """Delete stale sandbox records, orphaned directories, and temporary branches."""
    raise NotImplementedError
```

**Test stubs:**
Write a single-line contract docstring on every test stub with mandatory execution tier and test type: `[<tier>/<type>]` (referencing `docs/agents/testing.md#the-four-execution-tiers`). State the public symbol exercised, any private helpers covered, and the exact outcome contract asserted. End with `raise NotImplementedError`. The `### Tests` table indexes the tests (`Test`, `Tier`, `Outcome`); the stub docstring holds the exact assertion contract.

```python
class SandboxPruneCliIntegrationTests:
    def test_prune_empty_returns_nothing_to_prune(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        """[tier-3/integration] wt sandbox prune: empty sandboxes directory prints 'Nothing to prune'; exit 0."""
        raise NotImplementedError

    def test_prune_partial_failure_deletes_succeeded_items(
        self, cli_runner: CliRunner, sandbox_workspace: Path
    ) -> None:
        """[tier-3/integration] wt sandbox prune: partial failure deletes 'sbx_clean', reports error on 'sbx_locked'; exit 1."""
        raise NotImplementedError
```

Use absolute `worktree.*` imports at module top level and reference only symbols verified in Step 2.

### Decisions: The sole home for rationale

Record all design choices, rationale, and alternatives here:
- Format: `- **<decision point>:** <choice>, because <one clause>. Rejected: <alternative>. [🚨]`
- Append `🚨` if a decision requires confirmation.

### Edge cases: Genuine implementation gotchas only

Record non-obvious traps, execution gotchas, or sequencing constraints not already captured in Ground truth Traps or Decisions. Do not restate standard branch logic.

### Tests: Summary index table and contract stubs

Pair a concise summary index table with stubs carrying `[<tier>/<type>]` contract docstrings:

| Test | Tier | Outcome |
|---|---|---|
| `SandboxPruneCliIntegrationTests::test_prune_empty_returns_nothing_to_prune` | Tier 3 (integration) | exit 0; "Nothing to prune" |
| `SandboxPruneCliIntegrationTests::test_prune_partial_failure_deletes_succeeded_items` | Tier 3 (integration) | exit 1; succeeds on "sbx_clean", fails on "sbx_locked" |

```python
class SandboxPruneCliIntegrationTests:
    def test_prune_empty_returns_nothing_to_prune(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        """[tier-3/integration] wt sandbox prune: empty sandboxes directory prints 'Nothing to prune'; exit 0."""
        raise NotImplementedError

    def test_prune_partial_failure_deletes_succeeded_items(
        self, cli_runner: CliRunner, sandbox_workspace: Path
    ) -> None:
        """[tier-3/integration] wt sandbox prune: partial failure deletes 'sbx_clean', reports error on 'sbx_locked'; exit 1."""
        raise NotImplementedError
```

Assert exact contracts (literal JSON dict, exit code, filesystem state, or `*Result` fields). Ban vague phrasing (`"Verifies pruning works"`), piecewise assertions (`"Checks exit code is 0"`), and omitted fields.

### Single-ownership principle: what gets cut vs. kept

Assign each fact to exactly one owner and eliminate duplicates across sections:

| Element | Anti-pattern / Redundant | Standard |
|---|---|---|
| Header | Multi-paragraph prose essay | One line: `Planning only. Grounded against <base branch> at <short sha>.` |
| Contract | "Goal" prose, "As a user" stories | Verbatim FR-*/NFR-* list; no narrative paraphrasing |
| Ground truth cells | Multi-sentence implementation essays | One clause per cell max; `file:line` citation is the reference |
| Patterns & Traps | Repeated across Instructions or Edge cases | Ground truth section only |
| Instructions | Inline "because Y" explanations | Strictly imperative verbs; rationale in Decisions |
| Test stubs | Numbered steps, setup comments, body code | Single-line docstring with `[<tier>/<type>]` tag and exact outcome contract + `raise NotImplementedError` |
| Tests table | Bloated duplicate of stub details | Concise summary index (`Test`, `Tier`, `Outcome`) |
| Rule IDs | Cited then explained in prose | Rule ID only |
| Edge cases | Restating traps, decisions, or normal branches | Genuine implementation gotchas only |

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

1. Verify the plan against `docs/agents/REVIEW_CHECKLIST.json` for all rules matching touched paths or domains, ensuring zero BLOCKER violations. Do not add a compliance table to the plan.
2. Write the plan to `.agentic/plan.md` (overwriting any previous plan and deleting `.agentic/review.md`).
3. Report the plan path and state that planning is complete (no code implemented, tested, committed, or pushed).

---

## Self-check before handing off

Verify before presenting the plan:

- [ ] Header is `Planning only. Grounded against <base branch> at <short sha>.`
- [ ] Contract lists verbatim FR-*/NFR-* requirements with zero narrative paragraphs.
- [ ] Ground truth cells contain at most one clause per cell with exact `file:line` citations.
- [ ] Patterns and Traps appear only in Ground truth.
- [ ] Every FR and NFR maps to at least one artifact row with exact paths.
- [ ] Every new field, flag, default, and message matches the issue's Pre-determined data.
- [ ] Code samples use absolute `worktree.*` imports and reference verified symbols.
- [ ] Instructions use strictly imperative verbs with zero inline rationale.
- [ ] `### Decisions` holds all rationale; deviations flagged with `🚨`.
- [ ] Production stubs are signature + one-line docstring + `raise NotImplementedError`.
- [ ] Test stubs carry single-line `[<tier>/<type>]` docstrings with exact contracts + `raise NotImplementedError`.
- [ ] `### Tests` table is a concise summary index (`Test`, `Tier`, `Outcome`).
- [ ] Edge cases contain only genuine gotchas not captured in Traps or Decisions.
- [ ] Planned functions decompose below cognitive complexity <= 10.
- [ ] Zero BLOCKER violations against `docs/agents/REVIEW_CHECKLIST.json`.
