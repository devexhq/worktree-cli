"""Unit tests for worktree.core.doctor.checks.filesystem_writable."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from worktree.core.config.models import PathsConfig, ProjectConfig, WorktreeConfig
from worktree.core.doctor.checks.filesystem_writable import FilesystemWritableCheck
from worktree.core.doctor.models import CheckCategory, CheckStatus, DoctorContext
from worktree.core.project.models import ProjectIdentity
from worktree.core.project.services.identity import save_project_identity


class FilesystemWritableCheckTests:
    """Unit tests for FilesystemWritableCheck diagnostic outcomes."""

    def test_execute_all_configured_paths_writable_returns_ok(self, tmp_path: Path) -> None:
        """[tier-1/unit] FilesystemWritableCheck.execute: default PathsConfig, all dirs creatable -> OK with verified_paths."""
        config = WorktreeConfig(version=1, project=ProjectConfig(name="demo"))
        check = FilesystemWritableCheck()
        context = DoctorContext(cwd=tmp_path, config=config)

        result = check.execute(context)

        assert result.check_id == "filesystem.writable"
        assert result.category == CheckCategory.FILESYSTEM
        assert result.status == CheckStatus.OK
        assert result.error_code is None
        assert result.details == {
            "verified_paths": [
                str(tmp_path / ".worktree"),
                str(tmp_path / ".worktree/sessions"),
                str(tmp_path / ".worktree/artifacts"),
                str(tmp_path / ".worktree/sandboxes"),
                str(tmp_path / ".worktree"),
            ]
        }

    def test_execute_readonly_directory_returns_unwritable_failure(self, tmp_path: Path) -> None:
        """[tier-1/unit] FilesystemWritableCheck.execute: artifacts_dir pre-created read-only -> FAILED with DOCTOR_FS_UNWRITABLE."""
        artifacts_dir = tmp_path / ".worktree" / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.chmod(0o500)
        config = WorktreeConfig(version=1, project=ProjectConfig(name="demo"))
        check = FilesystemWritableCheck()
        context = DoctorContext(cwd=tmp_path, config=config)

        try:
            result = check.execute(context)
        finally:
            artifacts_dir.chmod(0o700)

        message = "1 configured path(s) are not writable."
        assert result.check_id == "filesystem.writable"
        assert result.category == CheckCategory.FILESYSTEM
        assert result.status == CheckStatus.FAILED
        assert result.error_code == "DOCTOR_FS_UNWRITABLE"
        assert result.details == {"unwritable_paths": [str(artifacts_dir)]}
        assert result.errors == [message]

    def test_execute_readonly_parent_directory_returns_unwritable_failure(self, tmp_path: Path) -> None:
        """[tier-1/unit] FilesystemWritableCheck.execute: cwd read-only, target dirs not yet created -> mkdir raises OSError -> FAILED with DOCTOR_FS_UNWRITABLE."""
        tmp_path.chmod(0o500)
        config = WorktreeConfig(version=1, project=ProjectConfig(name="demo"))
        check = FilesystemWritableCheck()
        context = DoctorContext(cwd=tmp_path, config=config)

        try:
            result = check.execute(context)
        finally:
            tmp_path.chmod(0o700)

        unwritable_paths = [
            str(tmp_path / ".worktree"),
            str(tmp_path / ".worktree/sessions"),
            str(tmp_path / ".worktree/artifacts"),
            str(tmp_path / ".worktree/sandboxes"),
            str(tmp_path / ".worktree"),
        ]
        message = f"{len(unwritable_paths)} configured path(s) are not writable."
        assert result.check_id == "filesystem.writable"
        assert result.category == CheckCategory.FILESYSTEM
        assert result.status == CheckStatus.FAILED
        assert result.error_code == "DOCTOR_FS_UNWRITABLE"
        assert result.details == {"unwritable_paths": unwritable_paths}
        assert result.errors == [message]

    def test_execute_missing_config_falls_back_to_default_paths(self, tmp_path: Path) -> None:
        """[tier-1/unit] FilesystemWritableCheck.execute: context.config=None -> probes PathsConfig() defaults."""
        check = FilesystemWritableCheck()
        context = DoctorContext(cwd=tmp_path, config=None)

        result = check.execute(context)

        defaults = PathsConfig()
        assert result.check_id == "filesystem.writable"
        assert result.category == CheckCategory.FILESYSTEM
        assert result.status == CheckStatus.OK
        assert result.error_code is None
        assert result.details == {
            "verified_paths": [
                str(tmp_path / defaults.root_dir),
                str(tmp_path / defaults.sessions_dir),
                str(tmp_path / defaults.artifacts_dir),
                str(tmp_path / defaults.root_dir / "sandboxes"),
                str((tmp_path / defaults.db_path).parent),
            ]
        }

    def test_execute_with_project_identity_probes_global_runtime_paths(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """An identified project probes global runtime paths and local workspace state."""
        global_root = tmp_path / "global"
        identity = ProjectIdentity(id="project-626", created_at=datetime(2026, 1, 1, tzinfo=UTC))
        config = WorktreeConfig(version=1, project=ProjectConfig(name="demo"))
        monkeypatch.setenv("WORKTREE_HOME", str(global_root))
        save_project_identity(tmp_path / ".worktree" / "project.json", identity)

        result = FilesystemWritableCheck().execute(DoctorContext(cwd=tmp_path, config=config))

        project_storage = global_root / "storage" / "projects" / "project-626"
        assert result.status == CheckStatus.OK
        assert result.details == {
            "verified_paths": [
                str(tmp_path / ".worktree"),
                str(project_storage / "sessions"),
                str(project_storage / "artifacts"),
                str(tmp_path / ".worktree" / "sandboxes"),
                str(tmp_path / ".worktree"),
            ]
        }
        assert not (tmp_path / ".worktree" / "sessions").exists()
        assert not (tmp_path / ".worktree" / "artifacts").exists()

    def test_execute_without_project_identity_probes_configured_legacy_runtime_paths(self, tmp_path: Path) -> None:
        """A legacy workspace probes its configured session and artifact directories."""
        config = WorktreeConfig(
            version=1,
            project=ProjectConfig(name="demo"),
            paths=PathsConfig(
                root_dir=".state",
                sessions_dir="runtime/sessions",
                artifacts_dir="runtime/artifacts",
                db_path=".state/data.db",
            ),
        )

        result = FilesystemWritableCheck().execute(DoctorContext(cwd=tmp_path, config=config))

        assert result.status == CheckStatus.OK
        assert result.details == {
            "verified_paths": [
                str(tmp_path / ".state"),
                str(tmp_path / "runtime" / "sessions"),
                str(tmp_path / "runtime" / "artifacts"),
                str(tmp_path / ".state" / "sandboxes"),
                str(tmp_path / ".state"),
            ]
        }
