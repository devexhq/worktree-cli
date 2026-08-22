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

**Suppression comments must use `# pyright: ignore[reportRuleName]`, not
`# type: ignore` or `# type: ignore[code]`.** Under this project's
`basedpyright` configuration, bare `# type: ignore` (with or without a code)
is **not honored** — the error still reports, and the comment gives a false
impression that it was acknowledged/suppressed. Verify any suppression
actually works by re-running `basedpyright src --level error` after adding
it; a comment that doesn't change the error count isn't suppressing anything.
Prefer fixing the underlying type issue over suppressing it — a common root
cause in this codebase is unpacking a "twin-optional" tuple return
(`tuple[T, None] | tuple[None, ErrorResult]`) into two independently-typed
local variables, where narrowing one (`if err is not None: return err`) does
not narrow the other; return a single object with one narrow-able field
instead.

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

**`basedpyright` is not currently a CI job.** [AGENTS.md](../../AGENTS.md)
states `basedpyright src --level error` must pass before committing, but
`ci.yml` only runs `test`, `lint`, and `complexity` — a type error introduced
on `main` (or merged via a PR that skipped the local check) will not fail CI
and can persist silently. Until a `typecheck` job is added to `ci.yml`, this
is an honor-system check: run `basedpyright src --level error` yourself
before every commit, and don't rely on a red CI run to catch a skipped one.

Match these locally (see [testing.md](testing.md) and the lint commands above)
before pushing to avoid CI failures.

## Migration hygiene

Before adding or changing anything under `core/db/` (a new table, column, or
repository method):

- **Every new table/column needs a real producer and a real consumer in
  `src/` in the same change**, not just its own unit tests. A repository
  method with zero call sites outside `tests/` (grep `src/` for the method
  name and the owning facade attribute) is a sign the feature landed without
  being wired up — either finish wiring it in the same PR or hold the
  schema/model/repository until the call site exists.
- **One-time data backfills are versioned Alembic revisions** (`op.execute()`
  with bound parameters), not ad-hoc raw-SQL Python functions that re-probe
  `sqlite_master`/`PRAGMA table_info` on every DB call regardless of whether
  the legacy data exists.
- **A hardcoded revision id string** (e.g. in a `command.stamp(...)` call) that
  duplicates a revision id already defined in an `alembic/versions/*.py` file
  is drift waiting to happen if that revision is ever renamed — derive it from
  the script directory instead of a second literal.
- Confirm any new/changed repository is actually constructed once per command
  invocation, not once per call — see
  [architecture.md](architecture.md#local-sqlite-datadb).

## Removing dead code

When a package/module is confirmed unused by the live CLI (see
[architecture.md](architecture.md#layers) — `core/task/` and `core/workflows/`
are the current example) and you're actually removing it, not just leaving the
"unused" note in place:

- **Confirm zero call sites first**, not just from the note in architecture.md —
  grep `src/` (excluding the package's own `services/`/`models.py`) for imports
  of the package and for its public functions/classes by name. A stale "unused"
  note that's actually gained a new caller since it was written is worse than no
  note at all.
- **Remove exception types and re-exports together with the code that raises
  them** — a `<X>LoadError`/`<X>ValidationError` left in `common/exceptions.py`
  or a package `__init__.py` after its only raiser is deleted is its own small
  piece of dead code.
- **Delete the package's tests in the same change**, not as a follow-up — tests
  for code that no longer exists don't provide coverage, they provide false
  confidence that something is still exercised.
- **Update every doc that named the package as unused-but-present** (this file,
  architecture.md's domain-ownership list and import-direction diagram,
  schemas-and-config.md's status callouts) in the same change — a "status:
  unused by the live CLI" note that outlives the code it was warning about is
  exactly the kind of doc drift [AGENTS.md](../../AGENTS.md#keeping-docs-accurate)
  asks you to avoid.
- If the package is being **consolidated into** a replacement rather than
  deleted outright (as `core/task/`/`core/workflows/` are candidates for
  merging into `core/blueprint/`), do the migration and the deletion in the same
  PR where practical — a long-lived "both exist, only one is live" state is
  exactly what produces the kind of duplicated-model drift this file's
  **Migration hygiene** section and
  [code-conventions.md](code-conventions.md#pydantic-models) both warn about.

## Versioning

Package versioning is dynamic via Hatchling + `hatch-vcs` in [pyproject.toml](../../pyproject.toml) (git tags). Runtime code reads it with `importlib.metadata.version("worktree-cli")` from [src/worktree/__init__.py](../../src/worktree/__init__.py) and [src/worktree/common/version.py](../../src/worktree/common/version.py).

## Release process

- [publish.yml](../../.github/workflows/publish.yml) publishes a release build to
  PyPI via `uv build` when a GitHub Release is published.
