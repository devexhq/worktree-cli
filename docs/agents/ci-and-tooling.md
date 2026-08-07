# CI and Tooling

## Lint and format

Config lives in [pyproject.toml](../../pyproject.toml) under `[tool.ruff]`
(Python 3.13, 88-char lines; rule sets `E, W, F, I, B, C4, UP, RUF, FA, D` with
Google-convention docstrings). There is no separate `ruff.toml`.
Run before pushing:

```bash
ruff check .
ruff format --check .   # use `ruff format .` to apply
```

## CI workflow

[.github/workflows/ci.yml](../../.github/workflows/ci.yml) runs three jobs on
push to `main` and on pull requests:

- `test`: `uv sync --all-extras` then pytest with coverage
  (`fail_under = 80` in [pyproject.toml](../../pyproject.toml)).
- `lint`: `uv run ruff check .` then `uv run ruff format --check .`.
- `ci`: gate job that fails if either `test` or `lint` failed.

Match these locally (see [testing.md](testing.md) and the lint commands above)
before pushing to avoid CI failures.

## Versioning

Static package versioning lives in [getworktree/__init__.py](../../getworktree/__init__.py) (`__version__ = "0.1.1"`), managed by Hatchling configured in [pyproject.toml](../../pyproject.toml).

## Release process

- [publish.yml](../../.github/workflows/publish.yml) publishes a release build to
  PyPI via `uv build` when a GitHub Release is published.
