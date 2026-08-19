# `wt workflow`

The `wt workflow` command discovers, lists, executes, and resumes workflow definitions.

## Subcommands

### `wt workflow` / `wt workflow list`

Lists recorded workflow sessions and available catalog workflow blueprints. Executing `wt workflow` without subcommands defaults to listing workflows.

```bash
wt workflow
```

### `wt workflow show`

Displays the session details and execution status of a specific workflow run session:

```bash
wt workflow show <session_id>
```

### `wt workflow run`

Executes a workflow blueprint end-to-end via the shared execution engine:

```bash
wt workflow run <name> [OPTIONS] [INPUTS...]
```

#### Arguments

* `name`: Logical workflow name registered in catalog storage or built-in templates.
* `INPUTS`: Trailing arguments forwarded as declared workflow input parameters.

#### Options

| Flag | Description |
| --- | --- |
| `--no-sandbox` | Run in-place without creating a Git sandbox. |
| `--keep` | Retain the sandbox worktree after workflow completion. |
| `--agent` | Override the default target agent adapter. |
| `--session-id` | Specify an explicit session identifier. |
| `--non-interactive` | Disable interactive failure prompts. Steps with `on_failure: prompt_user` abort instead of blocking on stdin. |


### `wt workflow resume`

Resumes a **paused** workflow session from its durable checkpoint:

```bash
wt workflow resume <session_id>
```

A tracked interactive `prompt_user` failure persists `status=paused` and a
`checkpoint_json` payload **before** waiting on the user. Resume reloads that
checkpoint, reuses the same sandbox when it still exists, skips successfully
completed steps, and always re-prompts at the pending `prompt_user` gate.

`completed_at` stays null while paused. `error_message` may hold a short pause
reason for `wt workflow show`; the checkpoint JSON is the source of truth for
resume.

Resume fails with a classified error (exit `1`) when:

| Case | Message |
| --- | --- |
| Unknown session | `Workflow session '<id>' not found.` |
| Status is not `paused` | `Cannot resume session '<id>': status is '<status>' (expected paused).` |
| Sandbox path missing | `Cannot resume session '<id>': sandbox path '<path>' no longer exists.` |
| Missing or corrupt checkpoint | `Cannot resume session '<id>': checkpoint is missing or corrupt.` |

Missing sandbox paths are hard failures — resume never silently creates a new
sandbox. Non-interactive `prompt_user` aborts and never leaves a run `paused`.

---

## Workflow YAML Definition Schema

Workflow blueprints live in `.worktree/workflows/<name>.yml`. Below
is an example matching the current Workflow Spec v1 schema
(`src/worktree/schemas/v1/workflow.json`):

```yaml
version: "1.0"
name: "fix-tests"
description: "Iteratively fix failing tests until they pass or attempts are exhausted"
timeout_seconds: 600

defaults:
  on_failure: continue

steps:
  - id: dev-cycle
    type: loop
    max_iterations: 5
    until:
      - "steps.run-tests.exit_code == 0"
    on_max_iterations: prompt_user
    do:
      - id: run-tests
        run: pytest
        on_failure: continue

      - id: ai-fix
        uses: wt/ai-code-patcher
        on_failure: abort
```

### Workflow Configuration Sections

| Key | Description |
| --- | --- |
| `version` | Must be `1` or `"1.0"`. |
| `name` | Required; workflow identifier (defaults `id` to `name` if omitted). |
| `description` | Optional human-readable summary. |
| `timeout_seconds` | Optional overall workflow timeout (`>= 1`). |
| `env` | Optional environment variables map. |
| `inputs` | Optional named input declarations (`description`, `required`, `default`). |
| `defaults` | Optional blueprint defaults. Currently only `defaults.on_failure`, which fills top-level standard steps that omit `on_failure` (fill-if-omitted; step-level values win). |
| `steps` | List of standard steps (`uses`/`run`, mutually exclusive) and/or `loop` blocks (`max_iterations`, `until`, `do`, `on_max_iterations`). |

### `on_failure`

Each standard step's `on_failure` accepts either a bare policy string or a configurable object:

```yaml
# Bare string form
on_failure: abort   # abort | continue | prompt_user | retry

# Object form (retry tuning + post-retry escalation)
on_failure:
  action: retry
  max_retries: 3
  backoff_ms: 500
  on_max_retries: abort   # abort | continue | prompt_user (no retry-on-retry)
```

Optional root-level `defaults.on_failure` uses the same string-or-object shape and
is applied only when a top-level standard step omits `on_failure`. Explicit step
`on_failure` always wins unchanged (no partial merge). This is inheritance only —
not a second post-step policy ladder.

`on_max_iterations` on `loop` blocks is always a bare string (`abort`, `continue`, or
`prompt_user` — `retry` is not valid there).

