# AGENTS.md

`Worktree` (`wt`) is a Typer-based CLI providing isolated Git worktree
developer workflows and AI agent workspaces, backed by a local `.worktree/` state
directory.

## Always-on docs
There are a subset of docs that must always be read for context before starting a task. **Open these files, read the docs  for context and treat their directives as authority**.
- docs/agents/architecture.md
- docs/agents/code-conventions.md
- docs/agents/schemas.md
- docs/agents/glossary.md
- docs/agents/testing.md

## Agentic process

Before executing commands or editing files, state:
    1. The specific directive/doc governing this action.
    2. The target scope (e.g. specific test package or module).

When implementing a GitHub issue, **plan before writing code**: follow
[docs/agents/planning.md](docs/agents/planning.md) to extract the issue's
contract, ground it in the current tree, and enumerate every artifact (DTOs,
services, facade methods, commands, subcommands, formatters, schemas, tests,
docs) into a plan with code samples. Skip it only for a single-file change that
adds no new surface.

## Essential commands

```bash
uv sync --all-extras            # install dependencies with uv (or uv pip install -e .[dev])
inv test                        # run tests (python -m pytest -n auto tests/ -q)
ruff check .                    # lint
ruff format .                   # format
basedpyright src tests          # typecheck package and tests (errors must be 0)
inv complexity --paths <changed-file1>,<changed-file2> --plain   # complexity gate for changed files
```

## Testing / Code Quality

Use `uv run inv test` during development. Prefer scoping to the test module/function during quick iterations. 
Before committing, all of these must pass:
`inv test -c` (coverage, **≥ 80%** via `fail_under` in `pyproject.toml`),
`ruff format`, `ruff check`, `basedpyright src tests --level error`,
`inv complexity --paths <changed-file1>,<changed-file2> --plain --failed` (no touched
function may exceed complexity 10). Fix any failure before retrying the commit
— do not commit while `inv complexity` is failing.

Coverage is a **backstop**, not a goal. Do **not** add tests only to raise the
percentage. Prefer tests that lock real behavior and regressions; see
[docs/agents/testing.md](docs/agents/testing.md).

Tests assert **contracts** (`BaseResult` objects, JSON payloads, exit codes,
files, git refs), never implementation (rendered layout, private state, call
order). Two rules an agent gets wrong by default: a test double must be a type
production actually passes, and a production parameter that only tests supply is
dead code. Cover every branch of a factory or dispatch chain - a covered line in
a two-branch function proves nothing. A coverage drop from deleting dead code is
a success. Full rules: [docs/agents/testing.md](docs/agents/testing.md).

Lint/format config lives in `pyproject.toml` under `[tool.ruff]` (no separate
`ruff.toml`).

`basedpyright` in this repo's config does **not** honor bare `# type: ignore`
or `# type: ignore[code]`. Only `# pyright: ignore[reportRuleName]` suppresses
anything: a bare `# type: ignore` on a real error is a silent no-op that
looks acknowledged but isn't. See
[ci-and-tooling.md](docs/agents/ci-and-tooling.md#type-checking).

### `Any`

`typeCheckingMode = "recommended"` means `reportAny` and `reportExplicitAny`
surface every `Any` as a **warning**, so they never block `--level error`. They
are still findings, not noise: triage each one you touch.

`Any` in a parameter costs checking inside one function. `Any` in a **return
type** disables checking at every call site, transitively, so `-> Any` is held
to a much stricter standard and is effectively never acceptable on a public
function. Prefer `object` when a value is only stored, compared, or passed
through: `object` forces a narrow before use, `Any` forces nothing.

Never reach for `Any` to work around an import boundary, a missing model, or a
test seam, fix the cause. If `Any` is the only way to satisfy a layering rule,
the class is in the wrong package. The four categories where `Any` is correct
(Pydantic `mode="before"` validators, serialization payloads, values read from
user documents, pass-through `**kwargs`) are listed in
[code-conventions.md](docs/agents/code-conventions.md#type-annotations-and-any).
Suppress only outside those four, and only with a reason.

### `pyright: ignore`

An ignore is not a type. `reportCallIssue`, `reportArgumentType`, and
`reportIncompatibleVariableOverride` are real errors; silencing them to
green `--level error` is how a defect stays. Fix the annotation, the
fixture, or the override.

The exceptions (intentional ill-typed test inputs, third-party stub
conflicts, platform-gated imports) are listed in
[code-conventions.md](docs/agents/code-conventions.md#type-checker-suppressions).
Every ignore needs a reason naming which one applies. Never use
`# type: ignore`; it is a no-op in this repo.

## Keeping user-facing docs in sync

`README.md`'s Quick start / command surface must match `wt --help` (i.e. the
`add_typer`/`register_*` calls in
[src/worktree/cli/cli.py](src/worktree/cli/cli.py)) exactly — no documented
command that doesn't exist, no shipped command left undocumented. When a
command is added, renamed, or removed in `cli.py`, update `README.md` in the
same PR. Prefer generating the comparison (diff `wt --help`'s command list
against the README) over eyeballing it.

## Backwards compatibility

Maintain backwards compatibility **only** for surfaces users interact with directly:
- CLI command surface, subcommands, arguments, and flags (e.g. renaming a sub-command).
- User configuration and schema files (e.g. keys or values in `.worktree/config.json`, blueprint YAMLs).
- Stable machine-readable CLI outputs (e.g. JSON event contracts).

Do **not** preserve backwards compatibility aliases, compatibility properties, or shim layers for internal code (`common/`, `core/`, or internal CLI modules). Update internal callers and test suites directly. If unsure whether a surface is user-facing, ask the user.

## Documentation

Update docs in the same PR only when the change matches one of these gates:

- **Package layout / ownership / import boundaries**: update
  [docs/agents/architecture.md](docs/agents/architecture.md) *structure*
  sections only (layers tree, domain ownership, boundaries). Do **not** append
  feature behavior essays there.
- **How to write Python in this repo** (models placement, Result/Outcome, DRY,
  errors): update [docs/agents/code-conventions.md](docs/agents/code-conventions.md).
- **User-visible CLI behavior**: update [docs/cli/](docs/cli/) (not architecture).
- **config.json / blueprint YAML fields / entity shapes**: update
 [docs/agents/schemas.md](docs/agents/schemas.md).
- **`core/db/` schema, tables, or migrations**: follow the migration hygiene
 checklist in
 [docs/agents/ci-and-tooling.md](docs/agents/ci-and-tooling.md#migration-hygiene)
 before merging — a new table/column needs a real caller in the same PR or an
 explicit note on why it's landing ahead of one.
- **Adding an agent provider**: follow
 [docs/agents/architecture.md](docs/agents/architecture.md#adding-a-new-agent-provider)
 and add its setup failure modes to
 [docs/agents/troubleshooting.md](docs/agents/troubleshooting.md).
- **Removing a package/subsystem**: follow
  [docs/agents/ci-and-tooling.md](docs/agents/ci-and-tooling.md#removing-dead-code).
- **Deleting a production symbol whose only caller was a test**: delete the test
  in the same PR and expect coverage to fall. Do not backfill tests to hold the
  percentage.

Keep docs lean: no update is better than busywork. Prefer **deleting stale
bullets** over appending a parallel truth. Pure refactors that do not change
public layout or ownership need no architecture.md diff.

### Keeping docs accurate

Docs go stale in a specific, avoidable way: a field table, model signature, or enum
list gets hand-copied from source, then the source changes and the doc doesn't
(there's no gate that would catch it — it's not covered by `ruff`/`basedpyright`/
tests). This has actually happened more than once (see
[schemas.md](docs/agents/schemas.md)'s history). Two rules
that prevent it, in priority order:

1. **Don't duplicate what a `Read` of the source already gives you unambiguously.**
   If a doc's job is to describe a Pydantic model's field names, types, and
   defaults, that's a smell — link to the model file/class instead and document
   only the behavior that *isn't* visible from the type hints (validators,
   resolution order, cross-field invariants, why a field exists). A doc earns its
   keep by capturing things assembled across multiple files, not by re-typing one
   file's contents in prose.
2. **When a field table genuinely can't be avoided** (it's the specification for
   something external, like a JSON Schema or a CLI's stable output format), add or
   extend a test that fails when the table and the source disagree, rather than
   trusting a future editor to remember to update both. A doc claim with no test
   behind it is a claim that will eventually be wrong.

If you're about to make an implementation decision based on a doc's stated field
list or model shape, and that doc doesn't point you at the source file, spot-check
the source before trusting it — the whole point of consulting the doc instead of
the source is trust, and that only holds if the doc holds up.

## Docs

| Doc | When to use |
|-----|-------------|
| [docs/agents/architecture.md](docs/agents/architecture.md) | Module layout, domain ownership, import boundaries, `.worktree/` layout (structure only) |
| [docs/agents/code-conventions.md](docs/agents/code-conventions.md) | Python style **and file placement** (`models.py` vs `services/`), Result/Outcome, writes, console output |
| [docs/agents/planning.md](docs/agents/planning.md) | Planning an issue before implementation (artifact inventory, code samples, plan template) |
| [docs/agents/testing.md](docs/agents/testing.md) | Adding or running tests |
| [docs/agents/schemas.md](docs/agents/schemas.md) | Entity shapes (exceptions, DTOs, facades, commands), config & blueprint schemas |
| [docs/agents/glossary.md](docs/agents/glossary.md) | Disambiguating task / workflow / blueprint / step / run / session / sandbox / checkpoint |
| [docs/agents/troubleshooting.md](docs/agents/troubleshooting.md) | Diagnosing agent-provider setup failures (missing keys, missing CLIs, timeouts) |
| [docs/agents/git-and-pr-conventions.md](docs/agents/git-and-pr-conventions.md) | Committing changes or opening a PR |
| [docs/agents/github-issues.md](docs/agents/github-issues.md) | Creating or updating GitHub issues (structure, tone, required sections) |
| [docs/agents/ci-and-tooling.md](docs/agents/ci-and-tooling.md) | Understanding lint/CI requirements or release versioning |
| [docs/cli/](docs/cli/) | Per-command reference (`wt catalog`, `wt run`, `wt config`, etc.) for user-facing behavior and flags |
