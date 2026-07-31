# Architecture

## Layers

```
getworktree/cli.py                 Typer entrypoint, wires flags to commands
getworktree/commands/<name>/       One package per CLI subcommand
  command.py                       Orchestration: calls core/common, handles typer.Exit
  dto.py                           Pydantic outcome model(s) for the command
  renderers.py                     Rich console rendering, kept out of command.py
getworktree/core/                  Business logic, no Typer/CLI concerns
  bootstrap.py                     Creates/repairs the .worktree/ directory tree
  config/{generator,manager}.py    Default config generation + load/validate
  db.py                            SQLite token-usage tracking
  git_sandbox.py                   Isolated `git worktree` sandbox lifecycle
  loops/seeder.py                  Seeds packaged starter loop YAML files
  templates/loops/*.yml            Packaged starter loop definitions
getworktree/common/                Shared, dependency-light helpers
  constants.py, fs.py, utils.py, schema_validation.py
getworktree/schemas/                Versioned JSON Schemas (config_v1.json, loop_v1.json)
```

Not every command has all three files (e.g. `status` has only `command.py`) — add
`dto.py`/`renderers.py` when a command's output/result grows non-trivial.

## Adding a new command

1. Create `getworktree/commands/<name>/{__init__.py,command.py}` (add `dto.py`/
   `renderers.py` once output grows past a couple of lines).
2. Implement `<name>_command(...)` in `command.py`, following the
   [Result/Outcome pattern](code-conventions.md) for anything that can partially fail.
3. Register it in [getworktree/cli.py](../../getworktree/cli.py) with `@app.command(name="...")`.
4. Add tests under `tests/commands/<name>/` mirroring [tests/commands/init](../../tests/commands/init).

## The `.worktree/` directory

`bootstrap_worktree` ([getworktree/core/bootstrap.py](../../getworktree/core/bootstrap.py))
creates this layout inside a Git repo, analogous to `.git/`:

```
.worktree/
  .meta/bootstrap.json   status, tool_version, initialized_at
  config.json            V1 config, validated against schemas/config_v1.json
  loops/                 seeded + user loop definitions (validated against loop_v1.json)
  sessions/, artifacts/, tmp/, logs/
  token_audit.db          SQLite token/cost ledger (getworktree/core/db.py)
```

Bootstrap is idempotent and never deletes user data; it only creates missing
subdirectories and repairs metadata.

## Sandboxes

`GitSandboxManager` / `sandbox_scope` ([getworktree/core/git_sandbox.py](../../getworktree/core/git_sandbox.py))
spawn real `git worktree` checkouts under `.worktree/sandboxes/<id>` on a throwaway
`worktree/sandbox-<id>` branch, bounded by `sandbox.max_active_sandboxes` from config.
Cleanup removes the worktree, deletes the branch, and prunes stale refs.

## Packaged resources

Schemas and loop templates ship inside the installed package and are read via
`importlib.resources.files(...)` (see `CONFIG_VALIDATOR`/`LOOP_VALIDATOR` in
`core/config/generator.py` and `core/loops/seeder.py`) rather than relative
filesystem paths, so they work correctly when installed as a wheel.
