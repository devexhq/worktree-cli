# `wt blueprint`

The `wt blueprint` command inspects, creates, deletes, and validates executable blueprint YAML files, resolved across four precedence tiers: REPO (`.worktree/catalog/blueprints/`), USER (`~/.worktree/user/catalog/blueprints/`), GLOBAL (`~/.worktree/global/catalog/blueprints/`), and PACKAGED (bundled starter templates). No SQLite index is involved — each disk-backed tier keeps its own `index.json`, rebuilt wholesale from a directory walk before every lookup, so a command always sees the current contents of disk.

`wt blueprint` requires an explicit subcommand; there is no bare-invocation default (unlike the retired `wt catalog`).

## Tier precedence

When a name or SHA matches more than one tier, the REPO copy wins, then USER, then GLOBAL, then PACKAGED. A REPO-tier blueprint shadowing a USER-tier blueprint of the same name is expected layering, not an error; a duplicate match *within the same tier* produces a warning instead.

## Subcommands

### `wt blueprint list` / `wt blueprint ls`

Lists blueprint items across all tiers, each row tagged with its resolved `tier`.

```bash
wt blueprint list [--format terminal|json]
wt blueprint ls [--format terminal|json]
```

### `wt blueprint create`

Creates a new blueprint file under the REPO tier only — `.worktree/catalog/blueprints/<name>.yml`, seeded from the packaged `default.yml` scaffold. There is no `--tier` flag; creating directly into USER or GLOBAL tiers is out of scope for this command.

```bash
wt blueprint create --name <name> [--format terminal|json]
```

### `wt blueprint show`

Displays metadata and YAML content for a blueprint, resolved via the tier precedence above and scoped to blueprints only (a same-named step is not returned).

```bash
wt blueprint show <sha_or_name> [--format terminal|json]
```

### `wt blueprint delete`

Deletes a REPO-tier blueprint file and reindexes that tier. A match resolved from USER or GLOBAL tier is refused with a "not deletable from this tier" error rather than deleted, since a repo-scoped command should never mutate shared state outside its own repository. Bundled templates in the `wt/` namespace (e.g. `wt/fix-tests`) are protected and cannot be deleted regardless of tier.

```bash
wt blueprint delete <sha_or_name> [--force] [--format terminal|json]
```

### `wt blueprint validate`

Validates a blueprint definition (YAML syntax, schema, and semantic invariants such as duplicate step IDs, undeclared input placeholders, and unsafe `script_path` values) without executing it. See [`CatalogValidateResult`](../agents/schemas.md) for the result shape and exit codes.

```bash
wt blueprint validate <target> [--format terminal|json]
```

`target` is a catalog name or namespaced identifier (e.g. `commit-plan`, `wt/fix-tests`), or a relative/absolute file path. Unlike the retired `wt catalog validate`, there is no `--type` option: the command name itself already fixes the type.
