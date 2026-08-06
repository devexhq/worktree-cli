# `wt template`

The `wt template` command inspects built-in blueprint definitions bundled with Worktree (`wt`). Built-in templates provide starting blueprints for workflows, tasks, and steps.

## Subcommands

### `wt template` / `wt template list` (Default)

Lists built-in templates. Running `wt template` without arguments defaults to listing available templates.

```bash
wt template
```

#### Options

* `--type [workflow|task|step]`: Filter templates by blueprint type.

```bash
# List only workflow templates
wt template list --type workflow

# List only task templates
wt template list --type task

# List only step templates
wt template list --type step
```

### `wt template show`

Displays the metadata and YAML definition of a specific built-in template:

```bash
wt template show <name> [OPTIONS]
```

#### Arguments

- `name`: Built-in template name (e.g. `feature-dev`, `run-tests`, `git-checkpoint`).

#### Options

* `--type [workflow|task|step]`: Optional blueprint type filter to disambiguate templates sharing the same name.

#### Examples

```bash
# Show details for the built-in feature-dev workflow template
wt template show feature-dev

# Show task template details
wt template show run-tests --type task
```
