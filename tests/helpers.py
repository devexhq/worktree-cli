import json
from pathlib import Path
from typing import Any

import yaml

from getworktree.core.config.generator import generate_default_config


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overrides into base, replacing (not merging) non-dict values."""
    result = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


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
            "use_git_worktree": True,
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
