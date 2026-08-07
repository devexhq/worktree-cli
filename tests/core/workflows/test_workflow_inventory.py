"""Tests for `getworktree.core.workflows.inventory`."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from getworktree.core.workflows.inventory import (
    WorkflowInventoryStatus,
    build_workflow_inventory,
)
from getworktree.core.workflows.seeder import seed_starter_workflows


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _template_text(name: str) -> str:
    root = resources.files("getworktree.core.templates.workflows")
    with root.joinpath(name).open(encoding="utf-8") as handle:
        return handle.read()


def _minimal_valid(name: str, description: str = "desc") -> str:
    return f"version: 1\nname: {name}\ndescription: {description}\n"


class BuildWorkflowInventoryTests:
    """Tests for build_workflow_inventory composition behavior."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        workflows_dir.mkdir()

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.status == WorkflowInventoryStatus.OK
        assert result.ok
        assert result.workflows_dir == workflows_dir.resolve()
        assert result.valid == []
        assert result.invalid == []
        assert result.errors == []
        assert result.warnings == []

    def test_all_valid_seeded_starters(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        assert seed_starter_workflows(workflows_dir).ok

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.ok
        assert result.invalid == []
        assert [entry.name for entry in result.valid] == [
            "fix-tests",
            "review-fix",
        ]
        assert all(entry.source_path.is_absolute() for entry in result.valid)
        assert len(result.valid) + len(result.invalid) == 2

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        assert seed_starter_workflows(workflows_dir).ok
        _write(workflows_dir / "broken.yml", "version: [\n")
        _write(workflows_dir / "noname.yml", "version: 1\ndescription: missing name\n")

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.ok
        assert result.errors == []
        assert [entry.name for entry in result.valid] == [
            "fix-tests",
            "review-fix",
        ]
        assert [entry.source_path.name for entry in result.invalid] == [
            "broken.yml",
            "noname.yml",
        ]
        assert result.invalid[0].name is None
        assert result.invalid[0].description is None
        assert result.invalid[0].status == "malformed_yaml"
        assert any("WORKFLOW_META_MALFORMED_YAML" in error for error in result.invalid[0].errors)
        assert any("WORKFLOW_META_MISSING_NAME" in error for error in result.invalid[1].errors)
        assert len(result.valid) + len(result.invalid) == 4

    def test_all_invalid(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "a.yml", "[]\n")
        _write(workflows_dir / "b.yml", "version: 2\nname: x\ndescription: d\n")

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.ok
        assert result.valid == []
        assert [entry.source_path.name for entry in result.invalid] == [
            "a.yml",
            "b.yml",
        ]
        assert len(result.valid) + len(result.invalid) == 2

    def test_discovery_failure_passthrough(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing-workflows"

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=missing)

        assert result.status == WorkflowInventoryStatus.DISCOVERY_FAILED
        assert not result.ok
        assert result.valid == []
        assert result.invalid == []
        assert result.workflows_dir == missing.resolve()
        assert any("WORKFLOW_DIR_NOT_FOUND" in error for error in result.errors)

    def test_valid_ordering_by_name_then_path(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "z.yml", _minimal_valid("beta"))
        _write(workflows_dir / "a.yml", _minimal_valid("alpha"))
        _write(workflows_dir / "m.yml", _minimal_valid("alpha", "second alpha"))

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.ok
        assert [(e.name, e.source_path.name) for e in result.valid] == [
            ("alpha", "a.yml"),
            ("alpha", "m.yml"),
            ("beta", "z.yml"),
        ]

    def test_invalid_ordering_by_filename(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "z-bad.yml", "[]\n")
        _write(workflows_dir / "a-bad.yml", "version: [\n")

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.ok
        assert [entry.source_path.name for entry in result.invalid] == [
            "a-bad.yml",
            "z-bad.yml",
        ]

    def test_duplicate_name_warnings(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "b.yml", _minimal_valid("fix-tests"))
        _write(workflows_dir / "a.yml", _minimal_valid("fix-tests", "other"))
        _write(workflows_dir / "solo.yml", _minimal_valid("unique"))

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.ok
        assert len(result.valid) == 3
        assert result.warnings == ["Duplicate workflow name 'fix-tests' in multiple files: a.yml, b.yml"]

    def test_invalid_entries_do_not_join_duplicate_warnings(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        workflows_dir.mkdir()
        _write(workflows_dir / "ok.yml", _minimal_valid("fix-tests"))
        _write(workflows_dir / "broken.yml", "version: [\n")

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.ok
        assert result.warnings == []
        assert len(result.invalid) == 1

    def test_unreadable_file_is_invalid_only(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "workflows"
        workflows_dir.mkdir()
        good = _write(workflows_dir / "good.yml", _minimal_valid("good-workflow"))
        secret = _write(workflows_dir / "secret.yml", _minimal_valid("secret-workflow"))
        secret.chmod(0)
        try:
            result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)
        finally:
            secret.chmod(0o600)

        assert result.ok
        if any(entry.source_path.name == "secret.yml" for entry in result.valid):
            # Root or environments that ignore file mode still keep inventory ok.
            assert [entry.name for entry in result.valid]
            return

        assert [entry.name for entry in result.valid] == ["good-workflow"]
        assert result.valid[0].source_path == good.resolve()
        assert len(result.invalid) == 1
        assert result.invalid[0].source_path.name == "secret.yml"
        assert result.invalid[0].status == "unreadable"

    def test_explicit_workflows_dir_does_not_need_config(self, tmp_path: Path) -> None:
        workflows_dir = tmp_path / "only"
        workflows_dir.mkdir()
        _write(workflows_dir / "one.yml", _template_text("fix-tests.yml"))

        result = build_workflow_inventory(cwd=tmp_path, workflows_dir=workflows_dir)

        assert result.ok
        assert [entry.name for entry in result.valid] == ["fix-tests"]
