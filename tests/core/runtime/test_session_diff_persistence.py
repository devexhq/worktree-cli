"""Integration tests for sandbox diff persistence during run_steps."""

from __future__ import annotations

from tests.helpers import GitFileSystem
from worktree.core.db import RunStatus
from worktree.core.diff import DiffService, DiffStatus
from worktree.core.runtime import ExecutionIdentity, RunContext, run_steps
from worktree.core.step import StepDefinition


class SessionDiffPersistenceTests:
    """Integration tests verifying diff.patch persistence during runtime execution."""

    def test_run_steps_persists_diff_patch_for_completed_run(self, git_fs: GitFileSystem) -> None:
        """Verify run_steps in a sandbox writes diff.patch before cleanup."""
        git_fs.init_repo()

        step = StepDefinition(
            id="step-edit",
            name="Edit file in sandbox",
            run="echo 'modified content' > file.txt",
        )

        identity = ExecutionIdentity(task_name="edit-task", task_sha="task_diff_1")
        outcome = run_steps(
            RunContext(
                steps=[step],
                cwd=git_fs.base_path,
                use_sandbox=True,
                identity=identity,
            )
        )

        assert outcome.status == RunStatus.COMPLETED
        patch_file = git_fs.base_path / ".worktree" / "sessions" / "task_diff_1" / "diff.patch"
        assert patch_file.is_file()
        content = patch_file.read_text(encoding="utf-8")
        assert "modified content" in content

        # Verify DiffService immediately reads the generated patch
        from worktree.common.utils import RichOutput

        diff_service = DiffService(path=git_fs.base_path, output=RichOutput(), session_id="task_diff_1")
        diff_res = diff_service.collect()
        assert diff_res.ok
        assert diff_res.status == DiffStatus.OK
        assert "modified content" in diff_res.diff_text

    def test_run_steps_persists_empty_diff_when_no_modifications(self, git_fs: GitFileSystem) -> None:
        """Verify run_steps writes empty diff.patch when sandbox made no file changes."""
        git_fs.init_repo()

        step = StepDefinition(
            id="step-read",
            name="Read-only step",
            run="echo 'no files modified'",
        )

        identity = ExecutionIdentity(task_name="read-task", task_sha="task_diff_empty")
        outcome = run_steps(
            RunContext(
                steps=[step],
                cwd=git_fs.base_path,
                use_sandbox=True,
                identity=identity,
            )
        )

        assert outcome.status == RunStatus.COMPLETED
        patch_file = git_fs.base_path / ".worktree" / "sessions" / "task_diff_empty" / "diff.patch"
        assert patch_file.is_file()
        assert patch_file.read_text(encoding="utf-8") == ""

    def test_run_steps_persists_diff_patch_for_failed_run(self, git_fs: GitFileSystem) -> None:
        """Verify run_steps writes diff.patch even when a subsequent step fails."""
        git_fs.init_repo()

        step_1 = StepDefinition(
            id="step-create",
            name="Create file",
            run="echo 'partial work' > partial.txt",
        )
        step_2 = StepDefinition(
            id="step-fail",
            name="Failing step",
            run="exit 1",
        )

        identity = ExecutionIdentity(task_name="fail-task", task_sha="task_diff_failed")
        outcome = run_steps(
            RunContext(
                steps=[step_1, step_2],
                cwd=git_fs.base_path,
                use_sandbox=True,
                identity=identity,
            )
        )

        assert outcome.status == RunStatus.FAILED
        patch_file = git_fs.base_path / ".worktree" / "sessions" / "task_diff_failed" / "diff.patch"
        assert patch_file.is_file()
        content = patch_file.read_text(encoding="utf-8")
        assert "partial work" in content
