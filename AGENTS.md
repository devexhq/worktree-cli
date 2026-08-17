# AGENTS.md

`Worktree` (`wt`) is a Typer-based CLI providing isolated Git worktree
developer workflows and AI agent workspaces, backed by a local `.worktree/` state
directory.

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

## Documentation

Update docs in the same PR only when the change matches one of these gates:

- **Package layout / ownership / import boundaries**: update
  [docs/agents/architecture.md](docs/agents/architecture.md) *structure*
  sections only (layers tree, domain ownership, boundaries). Do **not** append
  feature behavior essays there.
- **How to write Python in this repo** (models placement, Result/Outcome, DRY,
  errors): update [docs/agents/code-conventions.md](docs/agents/code-conventions.md).
- **User-visible CLI behavior**: update [docs/cli/](docs/cli/) (not architecture).
- **config.json / blueprint YAML fields**: update
  [docs/agents/schemas-and-config.md](docs/agents/schemas-and-config.md).

Keep docs lean: no update is better than busywork. Prefer **deleting stale
bullets** over appending a parallel truth. Pure refactors that do not change
public layout or ownership need no architecture.md diff.

## Docs

| Doc | When to use |
|-----|-------------|
| [docs/agents/architecture.md](docs/agents/architecture.md) | Module layout, domain ownership, import boundaries, `.worktree/` layout (structure only) |
| [docs/agents/code-conventions.md](docs/agents/code-conventions.md) | Python style **and file placement** (`models.py` vs `services/`), Result/Outcome, writes, console output |
| [docs/agents/testing.md](docs/agents/testing.md) | Adding or running tests |
| [docs/agents/schemas-and-config.md](docs/agents/schemas-and-config.md) | Changing `config.json` or workflow YAML schemas/defaults |
| [docs/agents/git-and-pr-conventions.md](docs/agents/git-and-pr-conventions.md) | Committing changes or opening a PR |
| [docs/agents/github-issues.md](docs/agents/github-issues.md) | Creating or updating GitHub issues (structure, tone, required sections) |
| [docs/agents/ci-and-tooling.md](docs/agents/ci-and-tooling.md) | Understanding lint/CI requirements or release versioning |
