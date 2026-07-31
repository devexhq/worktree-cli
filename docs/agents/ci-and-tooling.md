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

- `test`: `pip install -e .[dev]` then pytest with coverage
  (`fail_under = 80` in [pyproject.toml](../../pyproject.toml)).
- `lint`: `ruff check .` then `ruff format --check .`.
- `ci`: gate job that fails if either `test` or `lint` failed.

Match these locally (see [testing.md](testing.md) and the lint commands above)
before pushing to avoid CI failures.

## Versioning

`setup.py` defines `BASE_VERSION`. When `WORKTREE_DEV_BUILD=true` (set in CI for
non-release builds), the version becomes `{BASE_VERSION}.dev{GITHUB_RUN_NUMBER}`.
Bump `BASE_VERSION` for releases; keep it in sync with `__version__` in
[getworktree/cli.py](../../getworktree/cli.py).

## Release process

- [dev-publish.yml](../../.github/workflows/dev-publish.yml) publishes a dev build
  to PyPI automatically on every push to `main` (`WORKTREE_DEV_BUILD=true`).
- [publish.yml](../../.github/workflows/publish.yml) publishes a release build to
  PyPI when a GitHub Release is published.

Both run on every qualifying push/release with no manual approval step, so avoid
pushing to `main` with an unintentionally bumped `BASE_VERSION`.
