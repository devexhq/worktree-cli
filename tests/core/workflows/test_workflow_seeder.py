"""Tests for `getworktree.core.workflows.seeder`."""

from __future__ import annotations

from getworktree.core.workflows.seeder import seed_starter_workflows
from tests.helpers import FileSystem


class SeedStarterWorkflowsTests:
    """Tests for `seed_starter_workflows`."""

    def test_seed_starter_workflows_creates_missing_files(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"

        result = seed_starter_workflows(workflows_dir)

        assert result.ok
        assert {path.name for path in result.created_files} == {
            "fix-tests.yml",
            "review-fix.yml",
        }
        assert (workflows_dir / "fix-tests.yml").is_file()
        assert (workflows_dir / "review-fix.yml").is_file()

    def test_seed_starter_workflows_skips_existing_files_by_default(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        target = workflows_dir / "fix-tests.yml"
        target.write_text("custom\n", encoding="utf-8")

        result = seed_starter_workflows(workflows_dir)

        assert result.ok
        assert target in result.skipped_existing_files
        assert target.read_text(encoding="utf-8") == "custom\n"

    def test_seed_starter_workflows_overwrites_in_force_mode(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        target = workflows_dir / "review-fix.yml"
        target.write_text("custom\n", encoding="utf-8")

        result = seed_starter_workflows(workflows_dir, force=True)

        assert result.ok
        assert target in result.overwritten_files
        assert "version:" in target.read_text(encoding="utf-8")

    def test_seed_starter_workflows_handles_partial_existing_state(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        existing = workflows_dir / "fix-tests.yml"
        existing.write_text("custom\n", encoding="utf-8")

        result = seed_starter_workflows(workflows_dir)

        assert result.ok
        assert existing in result.skipped_existing_files
        assert (workflows_dir / "review-fix.yml") in result.created_files

    def test_seed_starter_workflows_reports_directory_collisions(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        target = workflows_dir / "fix-tests.yml"
        target.mkdir()

        result = seed_starter_workflows(workflows_dir)

        assert not result.ok
        assert any(str(target) in error for error in result.errors)
        assert (workflows_dir / "review-fix.yml") in result.created_files
