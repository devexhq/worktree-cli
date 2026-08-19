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


## Type checking

Config lives in [pyproject.toml](../../pyproject.toml) under `[tool.basedpyright]`
(`typeCheckingMode = "recommended"`, package `src/worktree/` only). `basedpyright`
is a dev dependency. Run:

```bash
basedpyright src
basedpyright src --level error   # errors only
```

First-pass noise from Typer defaults, unused callback params, Pydantic
`model_config`, and intentional discarded call results is silenced in config.
Warnings (especially `reportAny` / unknown types) remain visible; the current
gate target is **zero errors**.

## Complexity

`complexipy` is a dev dependency (`[project.optional-dependencies].dev` in
[pyproject.toml](../../pyproject.toml)) gating cognitive complexity per
function. Run it through the `inv complexity` task in
[tasks.py](../../tasks.py) rather than invoking the CLI directly:

```bash
inv complexity                                          # whole tree, rich output (matches CI)
inv complexity --paths src/worktree/cli/run/app.py       # scope to specific file(s), comma-separated
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
- `complexity`: diffs changed `src/*.py` files against the PR base
  (or previous commit on `main`) and runs `inv complexity` scoped to just
  those files — it does not fail on pre-existing complexity elsewhere in the
  tree.
- `ci`: gate job that fails if `test`, `lint`, or `complexity` failed.

Match these locally (see [testing.md](testing.md) and the lint commands above)
before pushing to avoid CI failures.

## Versioning

Package versioning is dynamic via Hatchling + `hatch-vcs` in [pyproject.toml](../../pyproject.toml) (git tags). Runtime code reads it with `importlib.metadata.version("worktree-cli")` from [src/worktree/__init__.py](../../src/worktree/__init__.py) and [src/worktree/common/version.py](../../src/worktree/common/version.py).

## Release process

- [publish.yml](../../.github/workflows/publish.yml) publishes a release build to
  PyPI via `uv build` when a GitHub Release is published.
