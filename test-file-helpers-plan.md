# tests/helpers.py Consolidation Plan

Status: **planning only** — no source files have been changed yet.

## Goal

Replace the ~20+ duplicated `mkdir(parents=True) + write_text(json.dumps/yaml str)`
blocks scattered across the test suite with one shared module: a single generic
file writer plus per-domain overridable factories, per docs/agents/testing.md's
"global helper with per-parameter override" convention.

## Module: `tests/helpers.py`

Plain importable module (not `conftest.py`) so call sites `import` it explicitly
rather than relying on fixture auto-discovery.

### Module-level merge helper

No standalone `write_file` free function — it's fully implemented on `FileSystem`
below. `_deep_merge` stays module-level since it's a pure dict algorithm, not
filesystem I/O, and both `FileSystem` and `GitFileSystem` methods use it
identically.

```python
def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overrides into base, replacing (not merging) non-dict values."""
    result = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

This lets nested overrides (e.g. `create_config_file(p, paths={"workflows_dir": "x"})`)
merge into the nested `paths` defaults instead of clobbering the whole sub-dict.

### `FileSystem` / `GitFileSystem` classes

**Decision:** factories are instance methods bound to a `base_path`. `write_file`
is fully implemented directly on `FileSystem` — no standalone free function
delegating to it. It previously existed as a Layer 1 free function purely
because the class design came second; once `fs`/`git_fs` are the standard entry
point for every test, the free function had exactly one caller
(`FileSystem.write_file` itself), which is unnecessary indirection. `_deep_merge`
remains free-standing since it's pure dict logic, unrelated to `base_path`.
Each factory takes an overridable `dir=` (relative to `base_path`) defaulting
to the real convention used by production code, plus `filename=` and
`**overrides` deep-merged into body defaults — so the common case needs
neither, and non-standard test layouts (e.g. discovery tests using a bare
`workflows/` dir instead of `.worktree/workflows/`) can still override.

```python
class FileSystem:
    """Writes test fixtures relative to a base_path."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def write_file(self, rel_path: str | Path, content: str | dict | list[Any]) -> Path:
        """Write content under base_path, creating parent dirs. Serializes dict/list by file suffix (.yaml/.yml/.json); str is written as-is."""
        path = self.base_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            text = content
        elif path.suffix in (".yaml", ".yml"):
            text = yaml.safe_dump(content, sort_keys=False)
        elif path.suffix == ".json":
            text = json.dumps(content, indent=2) + "\n"
        else:
            raise ValueError(f"write_file: cannot infer serialization for suffix {path.suffix!r}; pass content as str.")
        path.write_text(text, encoding="utf-8")
        return path

    def create_step_file(
        self,
        step_id: str = "lint",
        *,
        dir: str | Path = ".worktree/catalog/steps",
        filename: str | None = None,
        **overrides: Any,
    ) -> Path:
        defaults = {"id": step_id, "name": f"run-{step_id}", "type": "command", "command": "echo hi"}
        body = _deep_merge(defaults, overrides)
        return self.write_file(Path(dir) / (filename or f"{step_id}.yaml"), body)

    def create_config_file(self, *, filename: str = ".worktree/config.json", **overrides: Any) -> Path:
        defaults = {
            "version": 1,
            "project": {"name": "test-project"},
            "paths": {
                "root_dir": ".worktree",
                "workflows_dir": ".worktree/workflows",
                "sessions_dir": ".worktree/sessions",
                "artifacts_dir": ".worktree/artifacts",
                "db_path": ".worktree/data.db",
            },
        }
        body = _deep_merge(defaults, overrides)
        return self.write_file(filename, body)

    def create_workflow_file(
        self,
        name: str = "default-workflow",
        *,
        dir: str | Path = ".worktree/workflows",
        filename: str | None = None,
        **overrides: Any,
    ) -> Path:
        defaults = {
            "version": 1,
            "name": name,
            "description": "Test workflow",
            "steps": [{"id": "step-1", "type": "command", "command": "echo hi"}],
        }
        body = _deep_merge(defaults, overrides)
        return self.write_file(Path(dir) / (filename or f"{name}.yml"), body)

    def create_task_file(
        self,
        task_id: str = "default-task",
        *,
        dir: str | Path = ".worktree/catalog/tasks",
        filename: str | None = None,
        **overrides: Any,
    ) -> Path:
        # No TaskDefinition model exists yet (cli/task/command.py does ad hoc
        # yaml_data.get(...) parsing) - defaults mirror the loose dict shape it reads today.
        defaults = {
            "id": task_id,
            "name": task_id,
            "description": "Test task",
            "summary": "",
            "use_sandbox": True,
            "steps": ["echo hi"],
        }
        body = _deep_merge(defaults, overrides)
        return self.write_file(Path(dir) / (filename or f"{task_id}.yml"), body)


class GitFileSystem(FileSystem):
    """FileSystem rooted at a real git repo, see conftest.py's git_fs fixture."""

    def init_repo(self) -> Path:
        """Generate a valid .worktree/config.json (replaces the local _init_repo helper in test_workflow_resume_command.py)."""
        config_path = self.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        generate_default_config(config_path, project_name=self.base_path.name)
        return config_path
```

Examples:

```python
# Raw text (e.g. malformed-YAML negative tests keep this form)
fs.write_file("broken.yml", "version: [\n")

# Step file - replaces the block in test_resolve_uses_step_loads_referenced_definition
fs.create_step_file(step_id="lint", command="ruff check .")

# Config file - replaces config_path.parent.mkdir(...) + config_path.write_text(json.dumps(...))
git_fs.create_config_file(project={"name": "demo"}, sandbox={"max_active_sandboxes": 5})

# Workflow file - dir= override for tests that don't use the .worktree/ catalog layout
fs.create_workflow_file(name="fix-tests", description="Run and fix failing tests", dir="workflows")

# Task file
git_fs.create_task_file(task_id="run-lint", steps=["ruff check ."], use_sandbox=False)
```

## Fixtures: `fs` / `git_fs` (`git_repo` retired)

**Decision:** `conftest.py` gets two fixtures wrapping the classes above. No
autouse — most tests (config/db unit tests) don't touch the filesystem at all,
and `git_fs` does a real `copytree`, which isn't free.

```python
@pytest.fixture
def fs(tmp_path: Path) -> FileSystem:
    return FileSystem(tmp_path)


@pytest.fixture
def git_fs(tmp_path: Path, _git_repo_template: Path) -> GitFileSystem:
    target = tmp_path / "repo"
    shutil.copytree(_git_repo_template, target)
    return GitFileSystem(target)
```

**Decision:** `git_repo` is retired, not kept alongside `git_fs` — every current
usage is a pure Path pass-through (`git_repo / "..."`, `cwd=git_repo`,
`SandboxesDb(git_repo)`, `monkeypatch.chdir(git_repo)`; verified via grep across
all 16 consuming files), so every call site becomes `git_fs.base_path`. This is
a mechanical, word-boundary-safe rename (`\bgit_repo\b` → `git_fs.base_path`,
careful not to touch the distinct `_git_repo_template` fixture), verified by a
full `pytest` run afterward. `fs` has no legacy fixture to retire — it's purely
additive for `tmp_path`-based tests (`tests/core/step/*`, `tests/core/workflows/*`)
that want the factory methods without a real git repo.

Rule of thumb for which fixture a test needs: `fs` for `core/*` unit tests
(tmp_path only), `git_fs` for `cli/*` integration tests that exercise a real
`wt init`-style flow against a git repo.

## Rollout phases (separate commits/PRs, smallest first)

1. Land `tests/helpers.py` (`write_file`, `_deep_merge`, `FileSystem`,
   `GitFileSystem` — no call-site changes yet) — trivial, low risk.
2. `create_step_file` + migrate `tests/core/step/{test_resolver,test_loader,test_runner}.py`
   to the `fs` fixture (the file that motivated this).
3. Add `fs`/`git_fs` fixtures to `conftest.py`, retire `git_repo`: mechanical
   rename across all 16 consuming files (~118 call sites), plus swap
   `test_workflow_resume_command.py`'s local `_init_repo` for `git_fs.init_repo()`.
   Its own PR — larger mechanical diff, no behavior change, easy to review as a
   pure rename.
4. `create_config_file` + migrate config/init/sandbox/status/git_sandbox test files
   to `git_fs.create_config_file(...)`.
5. `create_workflow_file` + migrate `tests/core/workflows/*` (via `fs`),
   `tests/cli/workflow/*` (via `git_fs`).
6. `create_task_file` + migrate `tests/cli/task/*` (via `git_fs`).
7. Revisit a template factory only if real duplication shows up in
   `tests/cli/template/test_templates.py` (built-in templates are currently read
   from package resources, not usually written by tests).

Each phase: run scoped `pytest`, then before the final commit run `inv test -c`,
`ruff format .`, `ruff check .`, `inv complexity --paths tests/helpers.py,<migrated files> --plain --failed`.

## Open decisions

1. **PR granularity.** Recommend phases 1–2 in one PR (the concrete motivating
   case), phase 3 (`git_repo` retirement) as its own PR given the diff size,
   separate follow-up PRs for phases 4–6, rather than one large sweep.
2. **`write_file`'s `ValueError` on unknown suffix** — is a hard error the right
   call, or should it silently fall back to writing `str(content)`? Recommend
   keeping the error: it surfaces a factory/test bug (wrong path) immediately
   instead of writing unreadable output.
