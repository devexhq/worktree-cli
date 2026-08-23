"""Unit tests for resolve_and_load_task catalog loader."""

from __future__ import annotations

from tests.helpers import FileSystem
from worktree.common.models import DefinitionResolutionStatus
from worktree.core.catalog.services.inventory import ensure_catalog_dirs, scan_and_index_catalog
from worktree.core.task import TaskDefinition, resolve_and_load_task


class TaskLoaderTests:
    """Unit tests for resolving and loading task blueprints from the catalog."""

    def test_resolve_and_load_task_ok(self, fs: FileSystem) -> None:
        fs.write_file(
            ".worktree/catalog/tasks/run-lints.yml",
            {
                "name": "run-lints",
                "description": "Lint the project",
                "summary": "Ruff",
                "use_sandbox": False,
                "steps": [{"command": "ruff check ."}],
            },
        )
        scan_and_index_catalog(fs.base_path)

        result = resolve_and_load_task("run-lints", path=fs.base_path)

        assert result.ok
        assert result.status == DefinitionResolutionStatus.OK
        assert result.resolved is not None
        assert result.resolved.name == "run-lints"
        assert isinstance(result.definition, TaskDefinition)
        assert result.definition.name == "run-lints"
        assert result.definition.use_sandbox is False
        assert len(result.definition.steps) == 1
        assert result.definition.steps[0].id == "step-1"
        assert result.definition.steps[0].run == "ruff check ."

    def test_resolve_and_load_task_not_found(self, fs: FileSystem) -> None:
        ensure_catalog_dirs(fs.base_path)
        scan_and_index_catalog(fs.base_path)

        result = resolve_and_load_task("missing-task", path=fs.base_path)

        assert not result.ok
        assert result.status == DefinitionResolutionStatus.NOT_FOUND
        assert result.definition is None
        assert result.resolved is None
        assert any("not found" in err.lower() for err in result.errors)

    def test_resolve_and_load_task_malformed_yaml(self, fs: FileSystem) -> None:
        ensure_catalog_dirs(fs.base_path)
        fs.write_file(".worktree/catalog/tasks/broken.yml", "name: [unterminated\n")
        scan_and_index_catalog(fs.base_path)

        result = resolve_and_load_task("broken", path=fs.base_path)

        assert not result.ok
        assert result.status == DefinitionResolutionStatus.LOAD_ERROR
        assert result.definition is None
        assert len(result.errors) > 0

    def test_resolve_and_load_task_invalid_model(self, fs: FileSystem) -> None:
        fs.write_file(
            ".worktree/catalog/tasks/no-name.yml",
            {
                "description": "missing required name",
                "steps": [],
            },
        )
        scan_and_index_catalog(fs.base_path)

        result = resolve_and_load_task("no-name", path=fs.base_path)

        assert not result.ok
        assert result.status == DefinitionResolutionStatus.LOAD_ERROR
        assert result.definition is None
        assert any("validation" in err.lower() or "name" in err.lower() for err in result.errors)

    def test_resolve_and_load_task_package_exports(self) -> None:
        from worktree.core import task as task_pkg

        assert task_pkg.TaskDefinition is TaskDefinition
        assert callable(task_pkg.resolve_and_load_task)
        assert task_pkg.TaskLoadError.__name__ == "TaskLoadError"
        assert task_pkg.TaskValidationError.__name__ == "TaskValidationError"
