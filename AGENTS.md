# AGENTS.md

`getworktree` (`wt`) is a Typer-based CLI providing isolated Git worktree
developer workflows and AI agent workspaces, backed by a local `.worktree/` state
directory.

## Essential commands

```bash
uv sync --all-extras            # install dependencies with uv (or uv pip install -e .[dev])
inv test                        # run tests (python -m pytest tests/ -q)
ruff check .                    # lint
ruff format .                   # format
basedpyright getworktree         # typecheck package (errors must be 0)
inv complexity --paths <changed-file1>,<changed-file2> --plain   # complexity gate for changed files
```

## Testing / Code Quality

Use `pytest -q` during development. Prefer scoping to the test module/function during quick iterations. 
Before committing, all of these must pass:
`inv test -c` (coverage, **≥ 80%** via `fail_under` in `pyproject.toml`),
`ruff format`, `ruff check`, `basedpyright getworktree --level error`,
`inv complexity --paths <changed-file1>,<changed-file2> --plain --failed` (no touched
function may exceed complexity 10). Fix any failure before retrying the commit
— do not commit while `inv complexity` is failing.

Coverage is a **backstop**, not a goal. Do **not** add tests only to raise the
percentage. Prefer tests that lock real behavior and regressions; see
[docs/agents/testing.md](docs/agents/testing.md).

Lint/format config lives in `pyproject.toml` under `[tool.ruff]` (no separate
`ruff.toml`).

## Documentation

Update the relevant `docs/agents/*.md` in the same PR when behavior it describes
changes. Keep docs lean: no doc update is better than an update made just for
the sake of it, and stale content should be removed rather than left in place.

## Docs

| Doc | When to use |
|-----|-------------|
| [docs/agents/architecture.md](docs/agents/architecture.md) | Understanding module layout, the command pattern, or the `.worktree/` directory structure |
| [docs/agents/code-conventions.md](docs/agents/code-conventions.md) | Writing or reviewing Python code: Pydantic models, the Result/Outcome pattern, file writes, console output |
| [docs/agents/testing.md](docs/agents/testing.md) | Adding or running tests |
| [docs/agents/schemas-and-config.md](docs/agents/schemas-and-config.md) | Changing `config.json` or workflow YAML schemas/defaults |
| [docs/agents/git-and-pr-conventions.md](docs/agents/git-and-pr-conventions.md) | Committing changes or opening a PR |
| [docs/agents/github-issues.md](docs/agents/github-issues.md) | Creating or updating GitHub issues (structure, tone, required sections) |
| [docs/agents/ci-and-tooling.md](docs/agents/ci-and-tooling.md) | Understanding lint/CI requirements or release versioning |
