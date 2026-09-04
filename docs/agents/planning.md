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
- Copy **Pre-determined data** exactly. Field names, types, defaults, file
  paths, constants, error codes, and template bodies stated there are
  **normative**. You may not invent, rename, or "improve" them.
- Copy **Out of scope** verbatim into the plan's guardrail section. It is a stop
  sign, not a hint.
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
   neighbor beats designing from the docs.
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

Record the result as a ground-truth table (surface, `file:line`, what exists
today) in the plan.

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
  `*Formatter` class per module, implementing `to_rich` and
  `to_json_serializable`; shared table builders go in that domain's `common.py`.
  Wire it into `register_<domain>_formatters` and `__all__` in the domain
  `__init__.py`, which `register_all_formatters` already chains.
- **Config key** -> `core/config/models.py` plus `schemas/v1/config.json` plus
  the defaults generator, and state the default value.
- **JSON / YAML schema** -> `src/worktree/schemas/v1/*.json`, keeping
  `additionalProperties: false`.
- **DB model or migration** -> `core/db/models.py` plus an Alembic version. A
  new table or column needs a real caller in the same change set.
- **Tests** -> mirrored path under `tests/`, with the tier named per artifact:
  Tier 1 domain behavior, Tier 2 formatter (two tests: exact JSON dict and
  model-derived Rich values), Tier 3 CLI wiring (`*RootTests` and
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

Work one FR (or one testable clause of an FR) at a time. Under each: the ordered
instructions, then the code samples, then the decisions, then the edge cases.

### Code sample rules

Two kinds of sample, and the distinction matters:

**Write literal, final code for anything that is a contract.** Model and enum
definitions with every field, type, and default. Function and method signatures
with full type hints and a Google-style docstring. Typer argument and option
declarations with exact flag names and help text. Formatter class shells. Exact
JSON payload dicts. Exact error, warning, and fix strings. These leave no room
for interpretation, so spell them out.

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

**Write signature plus numbered pseudo-code for imperative bodies.** Give the
real signature and docstring, describe the body as numbered steps in comments,
and end with `raise NotImplementedError`. The logic is the implementer's job;
your job is to make the shape, the boundaries, and the order unambiguous.

```python
def prune_sandboxes(context: CliContext, dry_run: bool = False) -> SandboxPruneResult:
    """Prune stale sandbox records, orphaned directories, and temporary branches.

    Args:
        context: CLI context instance.
        dry_run: When True, report prunable items without deleting anything.
    """
    # 1. Load active sandbox records via context.db.sandboxes
    # 2. Diff records against on-disk worktrees to classify stale vs orphaned
    # 3. Return status=NOTHING_TO_PRUNE with an empty pruned_items when the diff is empty
    # 4. When dry_run, populate pruned_items and skip deletion
    # 5. Delete each item, collecting per-item failures into errors, and return
    raise NotImplementedError
```

Every sample must use absolute `worktree.*` imports at module top level and must
reference only symbols you actually read in Step 2. A sample that calls a helper
you did not verify exists is a bug you handed to someone else.

For each planned test, state the **exact contract asserted**: the exact dict for
JSON output, the exit code, the file or git ref on disk, the `*Result`
comparison. "Assert it works" is not a plan.

### Plan document template

````markdown
# Issue #<n>: <title>

Planning only, nothing was implemented. Grounded against `<base branch>` at
`<short sha>`.

## Contract

<Verbatim FR-*/NFR-* list with IDs. Pre-determined data reproduced exactly.>

### Out of scope (verbatim from the issue)

- ...

## Current state

| Surface | Location | What exists today |
|---|---|---|
| <surface> | `path:line` | <one clause> |

**Pattern to mirror:** <domain path chain, with citations>

**Traps (explicitly not touched):** <dead code, lookalike symbol, stale doc>

## Artifact inventory

| Artifact | Kind | Path | New or changed | Requirement |
|---|---|---|---|---|

Not needed for this issue: <kinds from the Step 3 checklist that are "none">

---

## FR-<n>: <name>

> <verbatim requirement text>

### Instructions

1. <exact file, exact symbol, exact change>

### Code

<literal contracts; signature-plus-pseudo-code bodies>

### Decisions

- **<decision point>:** <choice>, because <one clause>. Rejected: <alternative>.
  <🚨 if a reviewer should confirm this.>

### Edge cases

- <failure mode, default, or existing behavior a naive implementation misses>

### Tests

| Test | Tier | Path | Exact assertion |
|---|---|---|---|

---

## Cross-cutting

- **Docs gates that fire:** <specific docs, or "none" with the reason>
- **Validation:** `uv run inv test`, `ruff format .`, `ruff check .`,
  `basedpyright src --level error`,
  `inv complexity --paths <files> --plain --failed`
- **Open questions:** <blocking ambiguities, each flagged 🚨, or "none">
````

---

## Step 5: Save and hand off

Write the plan to `scratch/plans/<issue-number>-<slug>-plan.md` (`scratch/` is
gitignored, so plans stay out of commits). Create the directory if needed.

Report the path, and state plainly that this was planning only: nothing was
implemented, tested, committed, or pushed.

---

## Self-check before handing off

Do not hand off a plan that fails any of these:

- Every FR and NFR maps to at least one artifact row.
- Every artifact row has a real, exact path, verified to exist (or explicitly
  marked new).
- Every new field, flag, default, and message string traces to the issue's
  Pre-determined data or to a cited existing model.
- Every code sample's imports and referenced symbols were read in Step 2.
- No planned production symbol whose only consumer would be a test.
- No compatibility shim, alias, or dual code path unless the issue demanded one.
- Every Out of scope bullet is reproduced, and every trap found is marked
  not-touched.
- Every planned function decomposes below complexity 10.
- The validation commands listed are this repo's real ones, not guessed.
