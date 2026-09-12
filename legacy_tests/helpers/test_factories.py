"""Unit tests for persisted-record test factories."""

from pathlib import Path

from tests.helpers import CatalogHelper, FileSystem, RunFactory, make_checkpoint
from worktree.core.db import RunStatus, WorktreeDb


class RunFactoryTests:
    """Unit tests for repository-backed run fixture creation."""

    def test_create_persists_record_retrievable_by_session_id(self, tmp_path: Path) -> None:
        runs = RunFactory(WorktreeDb(path=tmp_path).runs)

        created = runs.create(session_id="history-1", blueprint_name="History", blueprint_key="history")

        assert runs.get("history-1") == created

    def test_create_paused_persists_catalog_identity_and_checkpoint(self, tmp_path: Path) -> None:
        fs = FileSystem(tmp_path)
        blueprint = CatalogHelper(fs).blueprint(key="resume", name="Resume blueprint")
        runs = RunFactory(WorktreeDb(path=tmp_path).runs)
        checkpoint = make_checkpoint()

        paused = runs.create_paused(
            session_id="resume-1",
            blueprint=blueprint.catalog_item,
            checkpoint=checkpoint,
        )

        assert paused.model_dump() == {
            "id": paused.id,
            "session_id": "resume-1",
            "blueprint_key": "resume",
            "blueprint_name": "Resume blueprint",
            "branch_name": "wt/resume",
            "status": RunStatus.PAUSED,
            "pid": None,
            "started_at": "2026-08-19 01:00:00",
            "completed_at": None,
            "error_message": "paused",
            "checkpoint_json": checkpoint.model_dump_json(),
        }

    def test_list_filters_persisted_records_by_status(self, tmp_path: Path) -> None:
        runs = RunFactory(WorktreeDb(path=tmp_path).runs)
        runs.create(session_id="completed", status=RunStatus.COMPLETED)
        runs.create(session_id="failed", status=RunStatus.FAILED)

        assert [record.session_id for record in runs.list(status=RunStatus.FAILED)] == ["failed"]
