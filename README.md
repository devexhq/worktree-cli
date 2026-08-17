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
wt workflow list
wt workflow show wf-12345
wt workflow run fix-tests
```

## Current command surface

### Top-level

- `wt init`
- `wt status`

### Config

- `wt config show`
- `wt config validate`

### Workflow

- `wt workflow list` (or `wt workflow`)
- `wt workflow show <id>`
- `wt workflow run <name>`
- `wt workflow resume <id>`

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

- Schemas and config: [docs/agents/schemas-and-config.md](docs/agents/schemas-and-config.md)
- Architecture: [docs/agents/architecture.md](docs/agents/architecture.md)

## Project status

This README reflects the currently implemented surface in `main`.
Additional commands may still be in progress.

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.

## Links

- Website: [devexhq.github.io/worktree-cli](https://devexhq.github.io/worktree-cli)
- Repository: [github.com/devexhq/worktree-cli](https://github.com/devexhq/worktree-cli)
