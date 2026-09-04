from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import click
import typer
import yaml
from rich.console import Console
from typer.core import TyperGroup

from worktree.cli.context import CliContext
from worktree.core.config.generator import generate_default_config
from worktree.core.db import (
    BlueprintKind,
    RunRecord,
    RunsRepository,
    RunStatus,
    SandboxesRepository,
    SandboxRecord,
    WorktreeDb,
)
from worktree.core.runtime import RunCheckpoint
from worktree.core.step import StepDefinition, StepResult


def make_cli_context(cwd: Path | None = None) -> CliContext:
    """Helper to construct a CliContext for test invocations."""
    effective_cwd = cwd or Path.cwd()
    return CliContext(
        cwd=effective_cwd,
        db=WorktreeDb(path=effective_cwd),
    )


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

    def write_file(self, rel_path: str | Path, content: str | dict[str, Any] | list[Any]) -> Path:
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
        config_path = self.base_path / filename
        config_path.parent.mkdir(parents=True, exist_ok=True)
        generate_default_config(config_path, project_name=self.base_path.name)
        if overrides:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            data = _deep_merge(data, overrides)
            config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return config_path

    def create_workflow_file(
        self,
        name: str = "default-workflow",
        *,
        dir: str | Path = ".worktree/catalog/workflows",
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
        """Write a task blueprint matching blueprint task shape."""
        defaults = {
            "name": task_id,
            "description": "Test task",
            "summary": "",
            "use_sandbox": True,
            "steps": [{"id": "step-1", "run": "echo hi"}],
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


def make_step_result(
    *,
    step_id: str = "step-1",
    status: str = "completed",
    exit_code: int = 0,
    stdout: str = "ok",
    stderr: str = "",
    duration_seconds: float = 0.01,
    **overrides: Any,
) -> StepResult:
    """Generate a valid StepResult with defaults for test assertions."""
    defaults: dict[str, Any] = {
        "step_id": step_id,
        "status": status,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": duration_seconds,
    }
    defaults.update(overrides)
    return StepResult(**defaults)


def make_ok_result(*, step_id: str = "step-1", **overrides: Any) -> StepResult:
    """Convenience helper for a successful completed StepResult."""
    return make_step_result(step_id=step_id, status="completed", exit_code=0, stdout="ok", stderr="", **overrides)


def make_failed_result(*, step_id: str = "step-1", **overrides: Any) -> StepResult:
    """Convenience helper for a failed StepResult."""
    defaults: dict[str, Any] = {
        "status": "failed",
        "exit_code": 1,
        "stdout": "",
        "stderr": "boom",
    }
    defaults.update(overrides)
    return make_step_result(step_id=step_id, **defaults)


def make_cmd_step(
    *,
    step_id: str = "s1",
    command: str = "echo ok",
    name: str | None = None,
    **overrides: Any,
) -> StepDefinition:
    """Generate a valid command StepDefinition."""
    defaults: dict[str, Any] = {
        "id": step_id,
        "name": name or f"Step {step_id}",
        "type": "command",
        "command": command,
    }
    defaults.update(overrides)
    return StepDefinition.model_validate(defaults)


def make_checkpoint(*, step_id: str = "step-1", **overrides: Any) -> RunCheckpoint:
    """Generate a valid RunCheckpoint instance with test defaults."""
    defaults: dict[str, Any] = {
        "version": 1,
        "next_step_index": 1,
        "step_results": [make_ok_result(step_id=step_id)],
        "sandbox_path": None,
        "use_sandbox": False,
        "keep": False,
        "pending_step_id": "step-2",
        "diagnostic": "",
        "pending_result": None,
    }
    defaults.update(overrides)
    return RunCheckpoint.model_validate(defaults)


def make_run(
    db: RunsRepository,
    session_id: str = "run-1",
    *,
    blueprint_name: str = "task-1",
    kind: BlueprintKind = BlueprintKind.TASK,
    status: RunStatus = RunStatus.COMPLETED,
    branch_name: str = "main",
    pid: int | None = None,
    started_at: str = "2026-08-19 01:00:00",
    completed_at: str | None = "2026-08-19 01:00:15",
    error_message: str | None = None,
    checkpoint_json: str | None = None,
) -> RunRecord:
    """Helper to insert a run row directly into RunsRepository with test defaults."""
    config_file = Path(str(db.path)) / ".worktree" / "config.json"
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        generate_default_config(config_file, project_name="test")
    db.create(
        session_id=session_id,
        blueprint_name=blueprint_name,
        kind=kind,
        branch_name=branch_name,
        status=RunStatus.RUNNING,
        pid=pid,
    )
    with db.session() as session:
        from sqlmodel import select

        item = session.exec(select(RunRecord).where(RunRecord.session_id == session_id)).first()
        if item is not None:
            item.status = status
            item.pid = pid
            item.started_at = started_at
            item.completed_at = completed_at
            item.error_message = error_message
            item.checkpoint_json = checkpoint_json
            session.add(item)
            session.commit()
    record = db.get(session_id)
    assert record is not None
    return record


def seed_sandbox(
    db: SandboxesRepository,
    sandbox_id: str = "sbx_1",
    *,
    name: str | None = None,
    path_suffix: str | None = None,
    create_dir: bool = True,
    base_commit: str = "4f2c9a1e8b3d6f0a2c5e7b1d9a3f6c8e0b2d4f6a",
) -> SandboxRecord:
    """Helper to create a sandbox record in SandboxesRepository for tests."""
    suffix = path_suffix if path_suffix is not None else sandbox_id
    sandbox_path = Path(str(db.path)) / ".worktree" / "sandboxes" / suffix
    if create_dir:
        sandbox_path.mkdir(parents=True, exist_ok=True)
    return db.create(
        id=sandbox_id,
        branch_name=f"worktree/sandbox-{sandbox_id}",
        base_commit=base_commit,
        sandbox_path=sandbox_path,
        name=name,
    )


def render_rich(renderable: Any, *, width: int = 160) -> str:
    """Render a Rich renderable directly to a plain text string for assertions."""
    buffer = StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        color_system=None,
        width=width,
    )
    console.print(renderable)
    return buffer.getvalue()


def get_subcommand(target: Any, *names: str) -> Any:
    """Resolve a nested Click Command from a Typer app or parent Click Group."""
    current = typer.main.get_command(target) if isinstance(target, typer.Typer) else target
    for name in names:
        assert isinstance(current, (click.Group, TyperGroup)), f"Expected Group, got {type(current)}"
        sub = current.commands.get(name)
        assert sub is not None, f"Command {name!r} not found on {current}"
        current = sub
    return current


def get_subgroup(target: Any, *names: str) -> Any:
    """Resolve a nested Click Group from a Typer app or parent Click Group."""
    cmd = get_subcommand(target, *names)
    assert isinstance(cmd, (click.Group, TyperGroup)), f"Expected Group, got {type(cmd)}"
    return cmd


def list_subcommands(group: Any) -> list[str]:
    """Return command names registered under a click Group."""
    assert isinstance(group, (click.Group, TyperGroup)), f"Expected Group, got {type(group)}"
    return sorted(group.commands.keys())
