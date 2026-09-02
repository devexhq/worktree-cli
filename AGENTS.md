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

## Agentic process

Before executing commands or editing files, state:
    1. The specific directive/doc governing this action.
    2. The target scope (e.g. specific test package or module).

## Essential commands

```bash
uv sync --all-extras            # install dependencies with uv (or uv pip install -e .[dev])
inv test                        # run tests (python -m pytest tests/ -q)
ruff check .                    # lint
ruff format .                   # format
basedpyright src                # typecheck package (errors must be 0)
inv complexity --paths <changed-file1>,<changed-file2> --plain   # complexity gate for changed files
```

## Testing / Code Quality

Use `pytest -q` during development. Prefer scoping to the test module/function during quick iterations. 
Before committing, all of these must pass:
`inv test -c` (coverage, **≥ 80%** via `fail_under` in `pyproject.toml`),
`ruff format`, `ruff check`, `basedpyright src --level error`,
`inv complexity --paths <changed-file1>,<changed-file2> --plain --failed` (no touched
function may exceed complexity 10). Fix any failure before retrying the commit
— do not commit while `inv complexity` is failing.

Coverage is a **backstop**, not a goal. Do **not** add tests only to raise the
percentage. Prefer tests that lock real behavior and regressions; see
[docs/agents/testing.md](docs/agents/testing.md).

Lint/format config lives in `pyproject.toml` under `[tool.ruff]` (no separate
`ruff.toml`).

`basedpyright` in this repo's config does **not** honor bare `# type: ignore`
or `# type: ignore[code]`. Only `# pyright: ignore[reportRuleName]` suppresses
anything — a bare `# type: ignore` on a real error is a silent no-op that
looks acknowledged but isn't. See
[ci-and-tooling.md](docs/agents/ci-and-tooling.md#type-checking).

## Keeping user-facing docs in sync

`README.md`'s Quick start / command surface must match `wt --help` (i.e. the
`add_typer`/`register_*` calls in
[src/worktree/cli/cli.py](src/worktree/cli/cli.py)) exactly — no documented
command that doesn't exist, no shipped command left undocumented. When a
command is added, renamed, or removed in `cli.py`, update `README.md` in the
same PR. Prefer generating the comparison (diff `wt --help`'s command list
against the README) over eyeballing it.

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
| [docs/agents/testing.md](docs/agents/testing.md) | Adding or running tests |
| [docs/agents/schemas.md](docs/agents/schemas.md) | Entity shapes (exceptions, DTOs, facades, commands), config & blueprint schemas |
| [docs/agents/glossary.md](docs/agents/glossary.md) | Disambiguating task / workflow / blueprint / step / run / session / sandbox / checkpoint |
| [docs/agents/troubleshooting.md](docs/agents/troubleshooting.md) | Diagnosing agent-provider setup failures (missing keys, missing CLIs, timeouts) |
| [docs/agents/git-and-pr-conventions.md](docs/agents/git-and-pr-conventions.md) | Committing changes or opening a PR |
| [docs/agents/github-issues.md](docs/agents/github-issues.md) | Creating or updating GitHub issues (structure, tone, required sections) |
| [docs/agents/ci-and-tooling.md](docs/agents/ci-and-tooling.md) | Understanding lint/CI requirements or release versioning |
| [docs/cli/](docs/cli/) | Per-command reference (`wt catalog`, `wt run`, `wt config`, etc.) for user-facing behavior and flags |
