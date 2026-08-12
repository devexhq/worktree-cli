"""Tests for `getworktree.core.workflows.resolve`."""

from __future__ import annotations

from pathlib import Path

from getworktree.core.workflows.resolve import (
    WorkflowResolveStatus,
    resolve_workflow_by_name,
)
from getworktree.core.workflows.seeder import seed_starter_workflows
from tests.helpers import FileSystem


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _minimal_valid(name: str, description: str = "desc") -> str:
    return f"version: 1\nname: {name}\ndescription: {description}\n"


class ResolveWorkflowByNameTests:
    """Tests for resolve_workflow_by_name classification and winner order."""

    def test_unique_valid_match(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        assert seed_starter_workflows(workflows_dir).ok

        result = resolve_workflow_by_name("fix-tests", cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.status == WorkflowResolveStatus.OK
        assert result.ok
        assert result.name == "fix-tests"
        assert result.workflows_dir == workflows_dir.resolve()
        assert result.entry is not None
        assert result.entry.name == "fix-tests"
        assert result.entry.source_path == (workflows_dir / "fix-tests.yml").resolve()
        assert result.matches == [result.entry]
        assert result.errors == []
        assert result.warnings == []

    def test_not_found_empty_directory(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()

        result = resolve_workflow_by_name("missing-workflow", cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.status == WorkflowResolveStatus.NOT_FOUND
        assert not result.ok
        assert result.entry is None
        assert result.matches == []
        assert any("WORKFLOW_RESOLVE_NOT_FOUND" in error for error in result.errors)
        assert "missing-workflow" in result.errors[0]
        assert workflows_dir.resolve().as_posix() in result.errors[0]
        assert "wt workflow list" in result.errors[0]

    def test_not_found_when_only_invalid_files(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "broken.yml", "version: [\n")
        _write(
            workflows_dir / "named-but-invalid.yml",
            "version: 2\nname: ghost\ndescription: bad version\n",
        )

        result = resolve_workflow_by_name("ghost", cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.status == WorkflowResolveStatus.NOT_FOUND
        assert result.entry is None
        assert result.matches == []
        assert any("WORKFLOW_RESOLVE_NOT_FOUND" in error for error in result.errors)

    def test_case_sensitive_name_match(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "ok.yml", _minimal_valid("fix-tests"))

        result = resolve_workflow_by_name("Fix-Tests", cwd=fs.base_path, workflows_dir=workflows_dir)

        # Uppercase fails name pattern before inventory (invalid_name).
        assert result.status == WorkflowResolveStatus.INVALID_NAME

        result_lower = resolve_workflow_by_name("fix-tests", cwd=fs.base_path, workflows_dir=workflows_dir)
        assert result_lower.ok
        assert result_lower.entry is not None

    def test_duplicate_names_deterministic_winner(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        later = _write(workflows_dir / "fix-tests.yaml", _minimal_valid("fix-tests", "yaml"))
        first = _write(workflows_dir / "fix-tests.yml", _minimal_valid("fix-tests", "yml"))
        other = _write(
            workflows_dir / "other-fix-tests.yml",
            _minimal_valid("fix-tests", "other"),
        )

        result = resolve_workflow_by_name("fix-tests", cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.status == WorkflowResolveStatus.OK
        assert result.ok
        assert result.entry is not None
        # Winner order: source_path.name, then full POSIX path.
        # fix-tests.yaml < fix-tests.yml < other-fix-tests.yml
        assert result.entry.source_path == later.resolve()
        assert [m.source_path.name for m in result.matches] == [
            "fix-tests.yaml",
            "fix-tests.yml",
            "other-fix-tests.yml",
        ]
        assert first.resolve() in {m.source_path for m in result.matches}
        assert other.resolve() in {m.source_path for m in result.matches}
        assert result.errors == []
        assert any("WORKFLOW_RESOLVE_DUPLICATE_NAME" in warning for warning in result.warnings)
        assert any("Duplicate workflow name 'fix-tests' in multiple files:" in warning for warning in result.warnings)
        resolver_warning = next(w for w in result.warnings if "WORKFLOW_RESOLVE_DUPLICATE_NAME" in w)
        assert "using 'fix-tests.yaml'" in resolver_warning
        assert "also found in:" in resolver_warning
        assert "fix-tests.yml" in resolver_warning
        assert "other-fix-tests.yml" in resolver_warning
        # Resolver warning is appended after inventory warnings.
        assert result.warnings[-1] == resolver_warning

    def test_duplicate_winner_by_filename_then_posix(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "b.yml", _minimal_valid("shared"))
        winner = _write(workflows_dir / "a.yml", _minimal_valid("shared", "a"))

        result = resolve_workflow_by_name("shared", cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.ok
        assert result.entry is not None
        assert result.entry.source_path == winner.resolve()
        assert [m.source_path.name for m in result.matches] == ["a.yml", "b.yml"]

    def test_discovery_failed_copies_inventory_errors(self, fs: FileSystem) -> None:
        missing = fs.base_path / "missing-workflows"

        result = resolve_workflow_by_name("fix-tests", cwd=fs.base_path, workflows_dir=missing)

        assert result.status == WorkflowResolveStatus.DISCOVERY_FAILED
        assert not result.ok
        assert result.entry is None
        assert result.matches == []
        assert result.workflows_dir == missing.resolve()
        assert any("WORKFLOW_DIR_NOT_FOUND" in error for error in result.errors)
        assert not any("WORKFLOW_RESOLVE_" in error for error in result.errors)

    def test_invalid_name_empty_string(self, fs: FileSystem) -> None:
        result = resolve_workflow_by_name("", cwd=fs.base_path, workflows_dir=fs.base_path / "workflows")

        assert result.status == WorkflowResolveStatus.INVALID_NAME
        assert result.name == ""
        assert result.entry is None
        assert result.matches == []
        assert any("WORKFLOW_RESOLVE_INVALID_NAME" in error for error in result.errors)
        assert result.workflows_dir.is_absolute()

    def test_invalid_name_whitespace_uppercase_underscore_pathlike(self, fs: FileSystem) -> None:
        cases = ["   ", "Bad_Name", "has_underscore", "../x", "a/b", "Fix-Tests"]
        for name in cases:
            result = resolve_workflow_by_name(name, cwd=fs.base_path, workflows_dir=fs.base_path / "workflows")
            assert result.status == WorkflowResolveStatus.INVALID_NAME, name
            assert result.name == name
            assert any("WORKFLOW_RESOLVE_INVALID_NAME" in e for e in result.errors), name
            assert "^[a-z0-9][a-z0-9-]*$" in result.errors[0]

    def test_invalid_name_does_not_require_workflows_dir(self, fs: FileSystem, monkeypatch) -> None:
        """Invalid name must not call inventory (no discovery IO)."""
        import getworktree.core.workflows.resolve as resolve_mod

        def _boom(*_args, **_kwargs):  # pragma: no cover - must not run
            raise AssertionError("build_workflow_inventory should not be called")

        monkeypatch.setattr(resolve_mod, "build_workflow_inventory", _boom)

        result = resolve_workflow_by_name("Bad_Name", cwd=fs.base_path)

        assert result.status == WorkflowResolveStatus.INVALID_NAME
        assert result.workflows_dir == (fs.base_path / ".worktree/workflows").resolve()

    def test_invalid_entries_never_win(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        good = _write(workflows_dir / "good.yml", _minimal_valid("alpha"))
        _write(
            workflows_dir / "bad.yml",
            "version: 1\nname: alpha\n",  # missing description → invalid
        )

        result = resolve_workflow_by_name("alpha", cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.ok
        assert result.entry is not None
        assert result.entry.source_path == good.resolve()
        assert len(result.matches) == 1
        assert result.warnings == []

    def test_pass_through_unrelated_inventory_warnings(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "a.yml", _minimal_valid("dup"))
        _write(workflows_dir / "b.yml", _minimal_valid("dup", "other"))
        solo = _write(workflows_dir / "solo.yml", _minimal_valid("solo"))

        result = resolve_workflow_by_name("solo", cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.ok
        assert result.entry is not None
        assert result.entry.source_path == solo.resolve()
        assert any("Duplicate workflow name 'dup' in multiple files:" in w for w in result.warnings)
        assert not any("WORKFLOW_RESOLVE_DUPLICATE_NAME" in w for w in result.warnings)

    def test_exported_from_package(self) -> None:
        from getworktree.core.workflows import (
            WorkflowResolveResult,
            WorkflowResolveStatus,
            resolve_workflow_by_name as exported,
        )

        assert exported is resolve_workflow_by_name
        assert WorkflowResolveStatus.OK.value == "ok"
        assert WorkflowResolveResult.model_fields["status"]
