"""Unit tests for worktree.core.doctor.checks.filesystem_writable."""

from pathlib import Path

from tests.harness import assert_model_equal
from worktree.core.config.models import PathsConfig, ProjectConfig, WorktreeConfig
from worktree.core.doctor.checks.filesystem_writable import FilesystemWritableCheck
from worktree.core.doctor.models import CheckCategory, CheckStatus, DiagnosticCheckResult, DoctorContext


class FilesystemWritableCheckTests:
    """Unit tests for FilesystemWritableCheck diagnostic outcomes."""

    def test_execute_all_configured_paths_writable_returns_ok(self, tmp_path: Path) -> None:
        """[tier-1/unit] FilesystemWritableCheck.execute: default PathsConfig, all dirs creatable -> OK with verified_paths."""
        config = WorktreeConfig(version=1, project=ProjectConfig(name="demo"))
        check = FilesystemWritableCheck()
        context = DoctorContext(cwd=tmp_path, config=config)

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="filesystem.writable",
                name="Filesystem Writable Check",
                category=CheckCategory.FILESYSTEM,
                status=CheckStatus.OK,
                message="All configured workspace paths are writable.",
                details={
                    "verified_paths": [
                        str(tmp_path / ".worktree"),
                        str(tmp_path / ".worktree/sessions"),
                        str(tmp_path / ".worktree/artifacts"),
                        str(tmp_path / ".worktree/sandboxes"),
                        str(tmp_path / ".worktree"),
                    ]
                },
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
                remediations=[],
            ),
        )

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
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="filesystem.writable",
                name="Filesystem Writable Check",
                category=CheckCategory.FILESYSTEM,
                status=CheckStatus.FAILED,
                message=message,
                details={"unwritable_paths": [str(artifacts_dir)]},
                duration_ms=0.0,
                error_code="DOCTOR_FS_UNWRITABLE",
                errors=[message],
                warnings=[],
                fixes=[],
                remediations=[],
            ),
        )

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
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="filesystem.writable",
                name="Filesystem Writable Check",
                category=CheckCategory.FILESYSTEM,
                status=CheckStatus.FAILED,
                message=message,
                details={"unwritable_paths": unwritable_paths},
                duration_ms=0.0,
                error_code="DOCTOR_FS_UNWRITABLE",
                errors=[message],
                warnings=[],
                fixes=[],
                remediations=[],
            ),
        )

    def test_execute_missing_config_falls_back_to_default_paths(self, tmp_path: Path) -> None:
        """[tier-1/unit] FilesystemWritableCheck.execute: context.config=None -> probes PathsConfig() defaults."""
        check = FilesystemWritableCheck()
        context = DoctorContext(cwd=tmp_path, config=None)

        result = check.execute(context)

        defaults = PathsConfig()
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="filesystem.writable",
                name="Filesystem Writable Check",
                category=CheckCategory.FILESYSTEM,
                status=CheckStatus.OK,
                message="All configured workspace paths are writable.",
                details={
                    "verified_paths": [
                        str(tmp_path / defaults.root_dir),
                        str(tmp_path / defaults.sessions_dir),
                        str(tmp_path / defaults.artifacts_dir),
                        str(tmp_path / defaults.root_dir / "sandboxes"),
                        str((tmp_path / defaults.db_path).parent),
                    ]
                },
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
                remediations=[],
            ),
        )
