---
name: wt-plan
description: >-
  Produce a human-reviewable implementation plan for a worktree-cli change,
  grounded in the current tree, with contracts written as literal final code and
  imperative bodies left as signature-plus-pseudo-code stubs. Writes the plan to
  .agentic/plan.md and implements nothing. Use when asked to plan a GitHub issue
  or a change before writing code, invoked as /wt-plan [<issue-number>].
---

# wt-plan

Produce one plan document, precise enough that a different agent with no memory of the issue could implement it correctly and a reviewer could audit the diff against it line by line.

`docs/agents/planning.md` is the authority for plan content. Read it first and follow its five steps. This skill covers the parts that doc does not: the reset, the tooling ban, and the hand-off.

## Hard boundaries

- **Never run tooling.** No `inv test`, no `pytest`, no `ruff`, no `basedpyright`, no `inv complexity`, no `uv sync`, no `wt` command. Read-only git (`git log`, `git diff`, `git show`, `git rev-parse`) and read-only `gh` (`gh issue view`, `gh repo view`) are the only commands you need.
- **Never edit `src/` or `tests/`.** The plan document is the entire deliverable. No commits, no pushes, no PR state.
- **Never plan from memory of the codebase.** Every path, symbol, and signature in the plan comes from a file you read in this session.

## Step 1: Reset the workspace

Before anything else, clear the previous cycle's artifacts so a stale review can never be read as current:

```bash
mkdir -p .agentic && rm -f .agentic/plan.md .agentic/review.md
```

## Step 2: Extract the contract

With an issue number: `gh issue view <number> --json number,title,body`.

Copy every `FR-*` and `NFR-*` verbatim with its ID, reproduce Pre-determined data exactly (field names, types, defaults, paths, constants, error codes, template bodies are normative), and copy `Out of scope` verbatim into the plan's guardrail section. Everything in scope is mandatory. Do not open or read sibling issues.

Without an issue number, restate the user's request as the contract in the same shape, and say plainly in the plan that the contract is a restatement rather than an issue body.

This project is greenfield: plan no compatibility shims, aliases, dual code paths, or deprecation windows unless the contract explicitly demands one.

## Step 3: Ground the plan in the tree

Read the always-on docs (`architecture.md`, `code-conventions.md`, `schemas.md`, `glossary.md`, `testing.md`), then read what exists today in every domain the change touches: `models.py`, `exceptions.py`, `facade.py`, `services/`, the CLI package, the formatters under `cli/ui/formatters/<domain>/`, and the mirrored tests.

Name the closest existing implementation you will mirror with `file:line` citations and follow it end to end. Copying a verified neighbor beats designing from the docs. Verify any doc field list against its source before relying on it, and record a stale doc as a trap rather than fixing it.

Record a ground-truth table (surface, `file:line`, what exists today), the pattern to mirror, and every trap a lower-context implementer could fall into, each marked explicitly out of scope.

## Step 4: Write the plan

Use the plan document template in `docs/agents/planning.md` (Step 4) exactly: Contract, Out of scope, Current state, Artifact inventory, then one section per FR with Instructions, Code, Decisions, Edge cases, Tests, then Cross-cutting. Walk the Step 3 artifact checklist and write `none` explicitly for every artifact kind the change does not need, so a reviewer can tell "not needed" from "forgotten".

The split between the two kinds of code sample is the point of this skill:

- **Contracts get literal, final code.** Model and enum definitions with every field, type, and default (including `model_config = {"extra": "forbid", "strict": True}`). Full signatures with type hints and Google-style docstrings. Typer argument and option declarations with exact flag names and help copy. Formatter class shells. Exact JSON payload dicts. Exact error, warning, and fix strings.
- **Imperative bodies get a stub.** Real signature, real docstring, the body as numbered steps in comments, ending in `raise NotImplementedError`. Do not write the working body: the logic is the implementer's job, and a plan that ships finished code cannot be reviewed as a plan.

Every sample uses absolute `worktree.*` imports at module top level and references only symbols you actually read. Decompose any function that would exceed cognitive complexity 10 into named helpers in the plan. For each planned test, state the exact contract asserted (exact dict, exit code, file or git ref, `*Result` comparison) and its tier.

When the contract leaves a detail genuinely unspecified, choose the option consistent with the nearest existing pattern, record the choice and the rejected alternative, and append 🚨 to that line.

## Step 5: Save and hand off

Write the plan to `.agentic/plan.md`.

Run the self-check list at the end of `docs/agents/planning.md` and do not hand off a plan that fails any item. Then report:

- the path (`.agentic/plan.md`) and a one-paragraph summary of the approach
- every open question and 🚨 decision, restated in chat so they are not missed in the file
- plainly, that this was planning only: nothing was implemented, tested, committed, or pushed

**A human reviews the plan before implementation.** Do not offer to start implementing in the same breath; stop and wait. `/wt-code` is what consumes the approved plan.
