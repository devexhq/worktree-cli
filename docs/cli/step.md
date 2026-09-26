# `wt step`

The `wt step` command inspects, creates, deletes, and validates executable step YAML files, resolved across four precedence tiers: REPO (`.worktree/catalog/steps/`), USER (`~/.worktree/user/catalog/steps/`), GLOBAL (`~/.worktree/global/catalog/steps/`), and PACKAGED (bundled starter templates). It mirrors `wt blueprint`'s command shapes and tier-resolution contract exactly, scoped to steps instead of blueprints — see [`wt blueprint`](blueprint.md) for the shared tier-precedence, index, and reindexing behavior.

`wt step` requires an explicit subcommand; there is no bare-invocation default.

## Subcommands

### `wt step list` / `wt step ls`

Lists step items across all tiers, each row tagged with its resolved `tier`.

```bash
wt step list [--format terminal|json]
wt step ls [--format terminal|json]
```

### `wt step create`

Creates a new step file, seeded from the packaged `default.yml` scaffold. By default it writes under the REPO tier (`.worktree/catalog/steps/<name>.yml`). Pass `--user` to write into the USER tier (`~/.worktree/user/catalog/steps/<name>.yml`) or `--global` for the GLOBAL tier (`~/.worktree/global/catalog/steps/<name>.yml`) instead; the two flags are mutually exclusive.

```bash
wt step create --name <name> [--user | --global] [--format terminal|json]
```

### `wt step show`

Displays metadata and YAML content for a step, resolved via tier precedence and scoped to steps only (a same-named blueprint is not returned).

```bash
wt step show <sha_or_name> [--format terminal|json]
```

### `wt step delete`

Deletes a REPO-tier step file and reindexes that tier. A match resolved from USER or GLOBAL tier is refused rather than deleted. Bundled templates in the `wt/` namespace are protected and cannot be deleted regardless of tier.

```bash
wt step delete <sha_or_name> [--force] [--format terminal|json]
```

### `wt step validate`

Validates a step definition (YAML syntax, schema, and semantic invariants such as an unsafe `script_path`) without executing it. See [`CatalogValidateResult`](../agents/schemas.md) for the result shape and exit codes.

```bash
wt step validate <target> [--format terminal|json]
```

`target` is a catalog name or namespaced identifier, or a relative/absolute file path. There is no `--type` option: the command name itself already fixes the type.
