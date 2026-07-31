# AGENTS.md

`getworktree` (`wt`) is a Typer-based CLI providing isolated Git worktree
developer loops and AI agent workspaces, backed by a local `.worktree/` state
directory.

## Essential commands

```bash
pip install -e .[dev]           # install with dev dependencies
inv test                        # run tests (python -m pytest tests/ -q)
ruff check .                    # lint
ruff format .                   # format
```

Use `inv test` during development. Before committing, all of these must pass:
`inv test -c` (coverage), `ruff format`, `ruff check`. Fix any failure before
retrying the commit.

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
| [docs/agents/schemas-and-config.md](docs/agents/schemas-and-config.md) | Changing `config.json` or loop YAML schemas/defaults |
| [docs/agents/git-and-pr-conventions.md](docs/agents/git-and-pr-conventions.md) | Committing changes or opening a PR |
| [docs/agents/ci-and-tooling.md](docs/agents/ci-and-tooling.md) | Understanding lint/CI requirements or release versioning |
