# Worktree CLI (`wt`)

[![CI](https://github.com/devexhq/worktree-cli/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/devexhq/worktree-cli/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/devexhq/worktree-cli.svg)](https://github.com/devexhq/worktree-cli/blob/main/LICENSE)
[![Issues](https://img.shields.io/github/issues/devexhq/worktree-cli.svg)](https://github.com/devexhq/worktree-cli/issues)
[![Last commit](https://img.shields.io/github/last-commit/devexhq/worktree-cli.svg)](https://github.com/devexhq/worktree-cli/commits/main)
[![PyPI version](https://img.shields.io/pypi/v/worktree-cli.svg)](https://pypi.org/project/worktree-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/worktree-cli.svg)](https://pypi.org/project/worktree-cli/)
[![Stars](https://img.shields.io/github/stars/devexhq/worktree-cli.svg?style=social)](https://github.com/devexhq/worktree-cli/stargazers)

Isolated git worktree developer workflows and autonomous AI agent workspaces.

Worktree helps humans and agents build, test, and remediate in parallel without disturbing your active local branch.

## Installation

```bash
pip install worktree-cli
```

Optional provider extras:

```bash
pip install "worktree-cli[cursor]"
```

## Requirements

- Python 3.13+
- Git
- For provider-specific workflow runs:
  - Cursor: `CURSOR_API_KEY` (+ `worktree-cli[cursor]`)
  - Gemini: Gemini CLI on `PATH` + `GEMINI_API_KEY`
  - Copilot: GitHub CLI (`gh`) on `PATH` + `GH_TOKEN` or `GITHUB_TOKEN`

## Quick start

```bash
wt init
wt status
wt config validate
wt catalog list
wt run fix-tests
wt history
```

## Current command surface

### Top-level

- `wt init`
- `wt status`
- `wt diff [session-id]` — view syntax-highlighted session diff
- `wt run <blueprint>` — execute a task or workflow blueprint
- `wt resume <session-id>` — resume a paused run
- `wt history [show <session-id>]` — list or inspect past runs

### Config

- `wt config show`
- `wt config set <key> <value>`
- `wt config validate`

### Catalog

- `wt catalog list` — list catalog blueprints/templates
- `wt catalog create` — create a new catalog blueprint
- `wt catalog show <sha-or-name>`
- `wt catalog delete <sha-or-name>`

### Sandbox

- `wt sandbox create`
- `wt sandbox list`
- `wt sandbox show <sandbox-id>`
- `wt sandbox prune` — safely prune stale sandboxes, orphaned directories, and temporary branches
- `wt sandbox delete <sandbox-id>`
- `wt sandbox apply <sandbox-id>` — apply sandbox changes back to workspace
- `wt sandbox diff <sandbox-id>` — inspect differences from base commit

## Agent providers for workflow runs

Workflow definitions support these providers:

- `local`
- `ollama`
- `cursor`
- `gemini`
- `copilot`

Provider behavior:

- `local` and `ollama` return unified diffs
- `cursor`, `gemini`, and `copilot` run as direct-mutation providers with shared safety gates before patches are accepted

## Project layout

Worktree initializes and uses:

- `.worktree/config.json`
- `.worktree/catalog/workflows/*.yml`
- `.worktree/catalog/tasks/*.yml`
- `.worktree/sessions/`
- `.worktree/artifacts/`

## Development

```bash
uv sync --all-extras
inv test
ruff format .
ruff check .
```

## Documentation

- Schemas and entities: [docs/agents/schemas.md](docs/agents/schemas.md)
- Architecture: [docs/agents/architecture.md](docs/agents/architecture.md)

## Project status

This README reflects the currently implemented surface in `main`.
Additional commands may still be in progress.

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.

## Links

- Website: [devexhq.github.io/worktree-cli](https://devexhq.github.io/worktree-cli)
- Repository: [github.com/devexhq/worktree-cli](https://github.com/devexhq/worktree-cli)
