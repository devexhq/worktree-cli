"""Integration tests for Engine session run.json persistence."""

from __future__ import annotations

from tests.helpers import GitFileSystem
from worktree.core.blueprint import Blueprint
from worktree.core.catalog import Catalog
from worktree.core.db import RunStatus, WorktreeDb
from worktree.core.engine import Engine, load_session_run
from worktree.core.engine.models import RunRequest


class EngineSessionPersistenceTests:
    """Integration tests verifying Engine persists run.json for runs and resumes."""

    def test_engine_run_persists_run_json(self, git_fs: GitFileSystem) -> None:
        """Verify Engine.run writes run.json with step results."""
        git_fs.init_repo()
        git_fs.write_file(
            ".worktree/catalog/tasks/test-task.yml",
            {
                "name": "test-task",
                "summary": "Test task persistence",
                "steps": [
                    {
                        "id": "step-1",
                        "name": "Echo step",
                        "run": "echo 'session step complete'",
                    }
                ],
            },
        )
        db = WorktreeDb(git_fs.base_path)
        catalog = Catalog(git_fs.base_path, db=db.catalog)
        engine = Engine(git_fs.base_path, db=db.runs, catalog=catalog)

        blueprint = Blueprint.load("test-task", catalog=catalog)

        request = RunRequest(session_id="task_persisted_1", use_sandbox=True)
        outcome = engine.run(blueprint, request)

        assert outcome.status == RunStatus.COMPLETED

        payload = load_session_run(git_fs.base_path, "task_persisted_1")
        assert payload is not None
        assert payload.session_id == "task_persisted_1"
        assert payload.name == "test-task"
        assert payload.kind == "task"
        assert payload.status == "completed"
        assert len(payload.step_results) == 1
        assert "session step complete" in payload.step_results[0].stdout
