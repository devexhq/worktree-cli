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

## Complexity

`complexipy` is a dev dependency (`[project.optional-dependencies].dev` in
[pyproject.toml](../../pyproject.toml)) gating cognitive complexity per
function. Run it through the `inv complexity` task in
[tasks.py](../../tasks.py) rather than invoking the CLI directly:

```bash
inv complexity                                          # whole tree, rich output (matches CI)
inv complexity --paths getworktree/cli/task/command.py  # scope to specific file(s), comma-separated
inv complexity --plain                                  # script-friendly output for agents
inv complexity --plain --failed                         # script-friendly output for agents, list failures only
```

Agents must run `inv complexity --paths <changed-file1>,<changed-file2> --plain --failed`
before committing and must not commit while it reports a failure. The task
wraps `complexipy <paths> --max-complexity-allowed 10` (add
`--suggest-refactors` for rich-mode refactor hints; ignored with `--plain`).
Treat any function you touch that fails the threshold as a required fix in
that PR, not a follow-up — see the "Structure" rules in
[code-conventions.md](code-conventions.md).
[complexipy-results.txt](../../complexipy-results.txt) is a stale point-in-time
snapshot predating this gate; don't treat it as current.

## CI workflow

[.github/workflows/ci.yml](../../.github/workflows/ci.yml) runs four jobs on
push to `main` and on pull requests:

- `test`: `uv sync --all-extras` then pytest with coverage
  (`fail_under = 80` in [pyproject.toml](../../pyproject.toml)).
- `lint`: `uv run ruff check .` then `uv run ruff format --check .`.
- `complexity`: diffs changed `getworktree/*.py` files against the PR base
  (or previous commit on `main`) and runs `inv complexity` scoped to just
  those files — it does not fail on pre-existing complexity elsewhere in the
  tree.
- `ci`: gate job that fails if `test`, `lint`, or `complexity` failed.

Match these locally (see [testing.md](testing.md) and the lint commands above)
before pushing to avoid CI failures.

## Versioning

Static package versioning lives in [getworktree/__init__.py](../../getworktree/__init__.py) (`__version__ = "0.1.1"`), managed by Hatchling configured in [pyproject.toml](../../pyproject.toml).

## Release process

- [publish.yml](../../.github/workflows/publish.yml) publishes a release build to
  PyPI via `uv build` when a GitHub Release is published.
