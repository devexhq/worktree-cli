# Planning Before Implementation

Read this **before writing any code** for a GitHub issue. Its output is a single
markdown plan file precise enough that a different agent, with no memory of the
issue, could implement it correctly, and a reviewer could audit the diff against
it line by line.

While planning you are **read-only**: do not edit `src/` or `tests/`, do not run
`inv test`, do not commit, push, or touch PR state. The plan document is the
entire deliverable.

## When to plan

Plan when the issue adds or changes any of: a command or subcommand, a
DTO/`*Result` model, a status enum, a domain exception, a service, a facade
method, a formatter, a config key, a JSON/YAML schema field, or a `core/db/`
table.

Skip planning only for a genuinely single-file, no-new-surface change (a typo, a
message string, a one-line branch fix).

---

## Step 1: Extract the contract from the issue

```bash
gh issue view <number> --json number,title,body
```

The issue body is the contract (see
[github-issues.md](github-issues.md)). Extract it, do not summarize it:

- Copy every `FR-*` and `NFR-*` **verbatim, with its ID**. Never paraphrase a
  requirement away. Paraphrase is how a clause gets dropped.
- **No discursive framing:** Stop at the verbatim FRs/NFRs. Do not add a "Goal"
  prose paragraph or "As a user" framing. The verbatim requirement list *is* the
  goal. Paraphrasing or adding narrative summaries introduces scope drift.
- Copy **Pre-determined data** exactly. Field names, types, defaults, file
  paths, constants, error codes, and template bodies stated there are
  **normative**. You may not invent, rename, or "improve" them.
- Copy **Out of scope** verbatim into the plan's guardrail section. It is a stop
  sign, not a hint.
- Copy any **Definition of Done** checklist verbatim from the issue body.
- Everything in scope is **mandatory**. There is no optional, stretch, or
  nice-to-have work in an issue body.
- **Do not open sibling issues.** The issue plus the in-repo docs it cites is
  sufficient by construction. Reading the issue tracker "for context" is scope
  creep.
- This project is **greenfield**: plan no compatibility shims, aliases, dual
  code paths, or deprecation windows unless the issue explicitly states a
  compatibility constraint. Replacing a superseded path and updating its callers
  in the same change set is the expected outcome.

If the issue leaves a detail genuinely unspecified, do not stall and do not
invent product behavior: choose the option consistent with the nearest existing
pattern found in Step 2, record the choice and the rejected alternative, and
append 🚨 to that line so a human catches it before implementation.

---

## Step 2: Ground yourself in the current code

Never plan against a memory of how the codebase works. Read it.

1. Read the always-on docs listed in [AGENTS.md](../../AGENTS.md)
   (architecture, code-conventions, schemas, glossary, testing).
2. For every domain the issue touches, read what exists today:
   - `src/worktree/core/<domain>/models.py`, `exceptions.py`, `facade.py`,
     `services/`
   - `src/worktree/cli/<name>/app.py` and `src/worktree/cli/<name>/commands/`
   - `src/worktree/cli/ui/formatters/<domain>/`
   - the mirrored tests under `tests/`
3. **Name the closest existing implementation you will mirror**, with
   `file:line` citations, and follow it end to end. Example: a new
   `wt config <verb>` mirrors `Config.set`
   (`src/worktree/core/config/mutate.py`) -> `ConfigSetResult` ->
   `config_set_command` (`src/worktree/cli/config/commands/config_set.py`) ->
   `ConfigSetFormatter`
   (`src/worktree/cli/ui/formatters/config/config_set.py`) -> registration in
   `src/worktree/cli/ui/formatters/config/__init__.py`. Copying a verified
   neighbor beats designing from the docs. When the plan reproduces a mirrored
   symbol's shape for reference, quote only its **signature and docstring**,
   never its full body — the `file:line` citation already points to the
   implementation, so the body adds nothing.
4. **Verify a doc's field list against the source before you rely on it.** Docs
   here go stale in one specific way: a table hand-copied from a model, then the
   model moved. Spot-check the source. (Known live example: `schemas.md` §4
   still describes a `formatters.py` and `renderers.py` inside each
   `cli/<name>/` package. Neither exists; formatters live under
   `cli/ui/formatters/<domain>/`.) If you find a stale doc claim, record it as a
   trap; fixing it is in scope only if an AGENTS.md doc gate says so.
5. If the issue's own description of current state does not match the tree, say
   so explicitly in the plan and give the corrected version. This is one of the
   most valuable things a plan can surface.
6. **Name every trap** a lower-context implementer could fall into: dead code, a
   similarly-named-but-unrelated symbol, a duplicate implementation, a stale
   doc. Mark each one explicitly out of scope so it is not touched by accident.
   (Follow `/wt-test-planner` Steps 1b–1d to audit dead status values and existing
   test coverage, ensuring dead enum paths are recorded as traps rather than tested.)

Record the result as a ground-truth table (`Surface`, `Location`, `What exists`)
in the plan:

- **One clause per cell, max.** The `file:line` citation is the reference —
  the cell should name what exists, not explain it. If an implementer needs
  more detail, they follow the citation. Never write multi-sentence narrative
  essays inside table cells.
- **Single ownership for patterns and traps:** "**Pattern to mirror**" and
  "**Traps (explicitly not touched)**" live in the Ground truth section and
  **only** here — never repeat them in Instructions, Decisions, or Edge cases.

---

## Step 3: Enumerate every artifact

Produce an inventory with one row per file you will touch. No row may say "e.g."
or "etc.": exact path, exact identifier.

| Artifact | Kind | Path | New or changed | Requirement |
|---|---|---|---|---|
| `SandboxPruneResult` | DTO | `src/worktree/core/sandbox/models.py` | new | FR-2 |

Then walk this checklist and write **"none"** explicitly for each kind the issue
does not need, so a reviewer can tell the difference between "not needed" and
"forgotten":

- **DTO / Result / Outcome** -> `core/<domain>/models.py`. Subclasses
  `BaseResult`, carries a `status` `StrEnum`, sets
  `model_config = {"extra": "forbid", "strict": True}`. Operations that can fail
  return a result, they do not raise.
- **Status enum** -> same `models.py`. Every value must be reachable from
  production and covered by a test.
- **Domain exception** -> `core/<domain>/exceptions.py`, subclassing the domain
  or `Definition*` base.
- **Service** -> `core/<domain>/services/<verb>.py` for imperative operations.
  Public models never live in `services/`.
- **Facade method** -> `core/<domain>/facade.py`, the domain's only public entry
  point.
- **Command handler** -> `cli/<name>/commands/<action>.py`: takes `CliContext`,
  returns the core `*Result`, calls
  `ui_dispatcher.dispatch(result, output_format=output_format)`. No `print`, no
  `rich` import, no `typer.echo` outside `cli/ui/`.
- **Typer registration** -> `cli/<name>/app.py`, plus `cli/cli.py` for a new
  top-level group. Exact flag names, exact `help=` copy, `raise typer.Exit(code=1)`
  when `not result.ok`.
- **Formatter** -> `cli/ui/formatters/<domain>/<name>.py`, exactly one
  `*Formatter` class per module, implementing `transform` and `to_rich`.
  `to_json_serializable` is inherited from `ComponentFormatter` and must not be
  overridden. Presentation view models live in
  `cli/ui/formatters/<domain>/<domain>_views.py` (or `<name>_view.py`) and are a
  required artifact for any formatter that derives values; shared table builders
  go in that domain's `common.py`. Wire it into `register_<domain>_formatters` and
  `__all__` in the domain `__init__.py`, which `register_all_formatters` already chains.
- **Config key** -> `core/config/models.py` plus `schemas/v1/config.json` plus
  the defaults generator, and state the default value.
- **JSON / YAML schema** -> `src/worktree/schemas/v1/*.json`, keeping
  `additionalProperties: false`.
- **DB model or migration** -> `core/db/models.py` plus an Alembic version. A
  new table or column needs a real caller in the same change set.
- **Tests** -> mirrored path under `tests/`, with the tier named per artifact:
  Tier 1 domain behavior, Tier 2 presentation contracts (three tests per formatter:
  transform equality against view model, exact literal JSON dict wire format, and
  view-derived Rich values), Tier 3 CLI wiring (`*RootTests` and
  `*CliIntegrationTests` are both required per command), Tier 4 `tests/lint/`
  invariants.
- **Docs** -> only the gates AGENTS.md lists: `docs/cli/` for user-visible
  behavior, `schemas.md` for entity or schema shapes, `architecture.md` for
  layout and ownership only, `README.md` when the command surface changes.

Every function you plan must hold cognitive complexity <= 10, so decompose the
work into named helpers **in the plan** rather than leaving one large body for
the implementer to untangle.

---

## Step 4: Write the plan

Work one FR (or one testable group of FRs) at a time. The fundamental rule:
**each fact in exactly one place**. Under each FR section:
1. `> <verbatim requirement text>`
2. `### Instructions`
3. `### Code`
4. `### Decisions`
5. `### Edge cases`
6. `### Tests`

> [!TIP]
> Use `/wt-test-planner --plan` to generate the `### Tests` table and stubs.
> The skill inspects the plan's Ground Truth and Artifact inventory, audits reachable status values, maps private helpers to public callers, and emits the exact two-column table and signature-only stubs ready to fold under this section.

### Instructions: Imperative verbs only

- Write instructions using strictly imperative verbs (e.g., "Create `...`", "Assert `...`").
- State **what** to do, not **why**. No "because", no rationale — that belongs exclusively in `### Decisions`.
- Do not restate what code samples or test tables already demonstrate.

### Code sample rules

Three kinds of sample, and the distinction matters:

**Write literal, final code for anything that is a contract.** Model and enum
definitions with every field, type, and default. Function and method signatures
with full type hints and a Google-style docstring. Typer argument and option
declarations with exact flag names and help text. Formatter class shells. Exact
JSON payload dicts. Exact error, warning, and fix strings. Non-obvious fixtures
and regex patterns. These leave no room for interpretation, so spell them out.

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

**Write signature plus a one-line intent docstring for production stubs.**
Give the real signature and a docstring that says what the function does, not
how, then end with `raise NotImplementedError`. No numbered steps, no body
code of any kind. The docstring adds nothing beyond what the signature and
name don't already say — it is not a place to restate the exact status/field
contract (the DTO and enum already pin that); it states intent.

```python
def prune_sandboxes(context: CliContext, dry_run: bool = False) -> SandboxPruneResult:
    """Delete stale sandbox records, orphaned directories, and temporary branches."""
    raise NotImplementedError
```

**Remove docstrings from test stubs entirely — the Tests table is the single source of truth.**
A test stub is merely a compiler-checkable placeholder (`raise NotImplementedError`). Do not
write docstrings on test stubs: any docstring is a second copy of the contract that will
drift or go stale. The `### Tests` table carries 100% of the verification contract (exact exit
codes, stdout substrings, disk/git mutations, and literal wire envelopes).

```python
# stubs — outcomes defined in the Tests table above
class SandboxPruneCliIntegrationTests:
    def test_prune_empty_returns_nothing_to_prune(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        raise NotImplementedError

    def test_prune_partial_failure_deletes_succeeded_items(
        self, cli_runner: CliRunner, sandbox_workspace: Path
    ) -> None:
        raise NotImplementedError
```

Every sample must use absolute `worktree.*` imports at module top level and must
reference only symbols you actually read in Step 2. A sample that calls a helper
you did not verify exists is a bug you handed to someone else.

### Decisions: The sole home for rationale

`### Decisions` is the single place where rationale, justifications, and trade-offs live:
- Use bullet format: `- **<decision point>:** <choice>, because <one clause>. Rejected: <alternative>. [🚨]`
- Absorb all "because X" clauses from instructions here.
- Flag any unspecified detail or deviation with 🚨.

### Edge cases: Genuine implementation gotchas only

- Record only non-obvious traps, execution gotchas, or sequencing constraints not already covered under `Traps` in Ground truth or `Decisions`.
- Do not restate standard happy/unhappy branch logic.

### Tests: Single source of truth table

The `### Tests` section folds directly from the output of `/wt-test-planner --plan`. It pairs a single-source-of-truth contract table with signature-only compiler-checkable Python stubs.

Use a clean two-column format: `| Test | Exact outcome |` (do not add redundant `Tier` or `Path` columns when the test path and tier are evident from context):

| Test | Exact outcome |
|---|---|
| `SandboxPruneCliIntegrationTests::test_prune_empty_returns_nothing_to_prune` | exit 0; "Nothing to prune" in stdout; no filesystem mutations |
| `SandboxPruneCliIntegrationTests::test_prune_partial_failure_deletes_succeeded_items` | exit 1; succeeds deleting "sbx_clean" but fails on "sbx_locked"; "Error pruning sbx_locked: permission denied" in stdout |

Followed directly by the compiler-checkable test stubs (zero docstrings):

```python
# stubs — outcomes in the Tests table above
class SandboxPruneCliIntegrationTests:
    def test_prune_empty_returns_nothing_to_prune(self, cli_runner: CliRunner, sandbox_workspace: Path) -> None:
        raise NotImplementedError

    def test_prune_partial_failure_deletes_succeeded_items(
        self, cli_runner: CliRunner, sandbox_workspace: Path
    ) -> None:
        raise NotImplementedError
```

The outcome in the table must be the **exact contract asserted**: the exact dict for JSON output, the exit code,
the file or git ref on disk, or the exact `*Result` field values. "Assert it works" is not a plan.
**Strictly ban conversational vagueness** (`"Verifies pruning works"`), **piecewise framing**
(`"Checks exit code is 0"`, `"Checks status is ok"`), and **silent exclusions** (omitting a field the test owns).

### Single-ownership principle: what gets cut vs. kept

Every piece of information in a plan must appear in exactly one place. The fix for bloated plans
is assigning each fact to exactly one owner and deleting every duplicate.

| Element | Anti-pattern / Redundant | Standard |
|---|---|---|
| Header | Multi-paragraph "nothing was implemented" essay | One line: `Planning only. Grounded against <branch> at <sha>.` |
| Contract | "Goal" prose, "As a user" stories | Verbatim FR-*/NFR-* list is the goal; no narrative paraphrasing |
| Ground truth cells | 3–5 sentence paragraphs explaining implementation | One clause per cell max; `file:line` citation is the reference |
| Patterns & Traps | Repeated across Ground truth, Instructions, Edge cases | Ground truth section only |
| Instructions | "Do X because Y" inline explanations | Strictly imperative verbs; rationale moved to Decisions |
| Test stubs | Full docstrings restating test outcomes | Zero docstrings; signature + `raise NotImplementedError` only |
| Tests contract | Split between stub docstrings, table, and ledger | `### Tests` table is the single source of truth (`Test` and `Exact outcome`) |
| Rule IDs | Cited then explained in prose | Rule ID only — implementer/reviewer reads the spec |
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

| Test | Exact outcome |
|---|---|
| `<TestClass>::<test_method>` | <exact exit code, stdout substring, disk/git state, or literal JSON envelope> |

```python
# stubs — outcomes in the Tests table above
class <TestClass>:
    def <test_method>(self, ...): raise NotImplementedError
```

---

## Cross-cutting

- **Docs gates that fire:** <specific docs, or "none" with the reason>
- **Validation:** `uv run inv test`, `uv run ruff format .`, `uv run ruff check .`, `uv run basedpyright src tests --level error`, `inv complexity --paths <files> --plain --failed`
- **Open questions:** <blocking ambiguities, each flagged 🚨, or "none">
````

---

## Step 5: Save and hand off

Before saving, sweep `docs/agents/REVIEW_CHECKLIST.json` for every rule
matching the touched paths or domains and verify the plan itself satisfies
every applicable BLOCKER clause — reread the actual planned imports, paths,
and stubs against each clause, not a restatement of the rule. Fix any
violation in the plan itself. This is a save gate, not a written report: no
compliance table belongs in `.agentic/plan.md`, only a plan with zero BLOCKER
violations.

Write the plan to `.agentic/plan.md` (`.agentic/` is gitignored, so plans stay
out of commits). Create the directory if needed. Exactly one plan exists at a
time: it is the handoff implementation reads, and the next planning cycle
replaces it along with any stale `.agentic/review.md`.

Report the path, and state plainly that this was planning only: nothing was
implemented, tested, committed, or pushed.

---

## Self-check before handing off

Do not hand off a plan that fails any of these:

- Header is a single line: `Planning only. Grounded against <base branch> at <short sha>.`
- Contract contains verbatim FR-*/NFR-* requirements with zero discursive "Goal" paragraphs or "As a user" narratives.
- Ground truth table cells contain at most one clause per cell with exact `file:line` citations.
- "Pattern to mirror" and "Traps (explicitly not touched)" live exclusively in Ground truth and are not repeated elsewhere.
- Every FR and NFR maps to at least one artifact row.
- Every artifact row has a real, exact path, verified to exist (or explicitly marked new).
- Every new field, flag, default, and message string traces to the issue's Pre-determined data or to a cited existing model.
- Every code sample's imports and referenced symbols were read in Step 2.
- No planned production symbol whose only consumer would be a test.
- No compatibility shim, alias, or dual code path unless the issue demanded one.
- Every Out of scope bullet is reproduced, and every trap found is marked not-touched.
- Instructions use strictly imperative verbs with zero inline rationale ("because X") or repeated code details.
- `### Decisions` is the sole owner of all rationale, choices, and rejected alternatives.
- Every production stub in `### Code` is signature + one-line intent docstring + `raise NotImplementedError` only — zero numbered steps or body code.
- Every test stub has **zero docstrings** and ends with `raise NotImplementedError` — the `### Tests` table is the single source of truth for exact outcomes.
- Every test's stated outcome in the `### Tests` table states the exact outcome in prose (exact status/field values, exit code, or wire dict), naming every field the test owns; zero vague phrasing (`"Verifies pruning works."`), zero piecewise framing (`"Checks exit code is 0."`), and zero silently dropped fields.
- Edge cases contain only genuine gotchas not already captured in Traps or Decisions.
- Every planned function decomposes below complexity 10.
- The validation commands listed are this repo's real ones, not guessed.
- Every rule in `docs/agents/REVIEW_CHECKLIST.json` matching the touched paths or domains was re-checked against the plan's actual content (not restated from memory), with zero BLOCKER violations remaining — and no compliance table was added to the plan to report it.
