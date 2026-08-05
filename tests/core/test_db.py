"""Tests for SQLite database tables, models, and CRUD helpers (Issue #134)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from getworktree.core.db import (
    RunStatus,
    TaskRunRecord,
    TemplateRecord,
    TemplateType,
    WorkflowRunRecord,
    get_task_run,
    get_template_by_id,
    get_template_by_path,
    get_workflow_run,
    init_database,
    insert_task_run,
    insert_workflow_run,
    list_task_runs,
    list_templates,
    list_workflow_runs,
    update_task_run_status,
    update_workflow_run_status,
    upsert_template,
)

DB_REL = ".worktree/data.db"


class TestDatabaseMigrations:
    """Tests for database initialization and schema creation."""

    def test_init_creates_tables_and_indexes(self, tmp_path: Path) -> None:
        db_path = init_database(cwd=tmp_path, db_rel_path=DB_REL)
        assert db_path.is_file()

        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }

        assert "templates" in tables
        assert "workflows" in tables
        assert "tasks" in tables

        assert "idx_templates_sha" in indexes
        assert "idx_templates_type" in indexes
        assert "idx_templates_path" in indexes
        assert "idx_workflows_session" in indexes
        assert "idx_workflows_status" in indexes
        assert "idx_tasks_session" in indexes
        assert "idx_tasks_status" in indexes

    def test_init_is_idempotent(self, tmp_path: Path) -> None:
        path1 = init_database(cwd=tmp_path, db_rel_path=DB_REL)
        path2 = init_database(cwd=tmp_path, db_rel_path=DB_REL)
        assert path1 == path2
        assert path1.is_file()


class TestTemplateCRUD:
    """Tests for template indexing CRUD helper functions."""

    def test_upsert_insert_and_get_by_id_and_path(self, tmp_path: Path) -> None:
        path = Path(".worktree/templates/workflow_a.yaml")
        rec = upsert_template(
            sha="workflow_1234567",
            template_type=TemplateType.WORKFLOW,
            path=path,
            checksum="hash1",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        assert isinstance(rec, TemplateRecord)
        assert rec.id == 1
        assert rec.sha == "workflow_1234567"
        assert rec.template_type is TemplateType.WORKFLOW
        assert rec.path == path
        assert rec.checksum == "hash1"
        assert rec.created_at
        assert rec.updated_at

        by_id = get_template_by_id(rec.id, cwd=tmp_path, db_rel_path=DB_REL)
        assert by_id == rec

        by_path = get_template_by_path(path, cwd=tmp_path, db_rel_path=DB_REL)
        assert by_path == rec

    def test_upsert_update_preserves_id_and_updates_sha_checksum(
        self, tmp_path: Path
    ) -> None:
        path = Path(".worktree/templates/task_b.yaml")
        first = upsert_template(
            sha="task_1111111",
            template_type=TemplateType.TASK,
            path=path,
            checksum="chk1",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        time.sleep(1.1)

        second = upsert_template(
            sha="task_2222222",
            template_type=TemplateType.TASK,
            path=path,
            checksum="chk2",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        assert second.id == first.id
        assert second.sha == "task_2222222"
        assert second.checksum == "chk2"
        assert second.created_at == first.created_at
        assert second.updated_at != first.updated_at

    def test_get_missing_template_returns_none(self, tmp_path: Path) -> None:
        assert get_template_by_id(999, cwd=tmp_path, db_rel_path=DB_REL) is None
        assert (
            get_template_by_path(Path("missing.yaml"), cwd=tmp_path, db_rel_path=DB_REL)
            is None
        )

    def test_list_templates_filtering(self, tmp_path: Path) -> None:
        upsert_template(
            sha="w1",
            template_type=TemplateType.WORKFLOW,
            path=Path("w1.yaml"),
            checksum="c1",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )
        upsert_template(
            sha="t1",
            template_type=TemplateType.TASK,
            path=Path("t1.yaml"),
            checksum="c2",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )
        upsert_template(
            sha="s1",
            template_type=TemplateType.STEP,
            path=Path("s1.yaml"),
            checksum="c3",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        all_templates = list_templates(cwd=tmp_path, db_rel_path=DB_REL)
        assert len(all_templates) == 3

        workflows = list_templates(
            template_type=TemplateType.WORKFLOW, cwd=tmp_path, db_rel_path=DB_REL
        )
        assert len(workflows) == 1
        assert workflows[0].sha == "w1"

        steps = list_templates(template_type="step", cwd=tmp_path, db_rel_path=DB_REL)
        assert len(steps) == 1
        assert steps[0].sha == "s1"

    def test_invalid_template_type_raises_value_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="constraint"):
            upsert_template(
                sha="invalid",
                template_type="invalid_type",  # type: ignore[arg-type]
                path=Path("invalid.yaml"),
                checksum="c",
                cwd=tmp_path,
                db_rel_path=DB_REL,
            )


class TestWorkflowRunCRUD:
    """Tests for workflow run CRUD helper functions."""

    def test_insert_and_get_workflow_run(self, tmp_path: Path) -> None:
        rec = insert_workflow_run(
            session_id="wf_session_1",
            workflow_name="dev-workflow",
            branch_name="feature/workflow",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        assert isinstance(rec, WorkflowRunRecord)
        assert rec.id == 1
        assert rec.session_id == "wf_session_1"
        assert rec.workflow_name == "dev-workflow"
        assert rec.branch_name == "feature/workflow"
        assert rec.status is RunStatus.RUNNING
        assert rec.started_at
        assert rec.completed_at is None
        assert rec.error_message is None

        fetched = get_workflow_run("wf_session_1", cwd=tmp_path, db_rel_path=DB_REL)
        assert fetched == rec

    def test_insert_duplicate_session_id_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        insert_workflow_run(
            session_id="dup_wf",
            workflow_name="wf",
            branch_name="b",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        with pytest.raises(ValueError, match="already exists"):
            insert_workflow_run(
                session_id="dup_wf",
                workflow_name="wf",
                branch_name="b",
                cwd=tmp_path,
                db_rel_path=DB_REL,
            )

    def test_get_missing_workflow_run_returns_none(self, tmp_path: Path) -> None:
        assert (
            get_workflow_run("non_existent", cwd=tmp_path, db_rel_path=DB_REL) is None
        )

    def test_update_workflow_run_status(self, tmp_path: Path) -> None:
        insert_workflow_run(
            session_id="wf_to_update",
            workflow_name="wf",
            branch_name="b",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        updated = update_workflow_run_status(
            session_id="wf_to_update",
            status=RunStatus.FAILED,
            error_message="Execution timeout",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        assert updated is not None
        assert updated.status is RunStatus.FAILED
        assert updated.completed_at is not None
        assert updated.error_message == "Execution timeout"

    def test_update_missing_workflow_run_returns_none(self, tmp_path: Path) -> None:
        assert (
            update_workflow_run_status(
                session_id="missing",
                status=RunStatus.COMPLETED,
                cwd=tmp_path,
                db_rel_path=DB_REL,
            )
            is None
        )

    def test_invalid_workflow_status_raises_value_error(self, tmp_path: Path) -> None:
        insert_workflow_run(
            session_id="wf_invalid_status",
            workflow_name="wf",
            branch_name="b",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        with pytest.raises(ValueError, match="constraint"):
            update_workflow_run_status(
                session_id="wf_invalid_status",
                status="invalid_status",  # type: ignore[arg-type]
                cwd=tmp_path,
                db_rel_path=DB_REL,
            )

    def test_list_workflow_runs(self, tmp_path: Path) -> None:
        insert_workflow_run(
            session_id="wf_1",
            workflow_name="wf1",
            branch_name="b1",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )
        insert_workflow_run(
            session_id="wf_2",
            workflow_name="wf2",
            branch_name="b2",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        runs = list_workflow_runs(cwd=tmp_path, db_rel_path=DB_REL)
        assert len(runs) == 2
        assert {r.session_id for r in runs} == {"wf_1", "wf_2"}


class TestTaskRunCRUD:
    """Tests for task run CRUD helper functions."""

    def test_insert_and_get_task_run(self, tmp_path: Path) -> None:
        rec = insert_task_run(
            session_id="task_session_1",
            task_name="lint-fix",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        assert isinstance(rec, TaskRunRecord)
        assert rec.id == 1
        assert rec.session_id == "task_session_1"
        assert rec.task_name == "lint-fix"
        assert rec.status is RunStatus.RUNNING
        assert rec.started_at
        assert rec.completed_at is None
        assert rec.error_message is None

        fetched = get_task_run("task_session_1", cwd=tmp_path, db_rel_path=DB_REL)
        assert fetched == rec

    def test_insert_duplicate_task_session_id_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        insert_task_run(
            session_id="dup_task",
            task_name="task",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        with pytest.raises(ValueError, match="already exists"):
            insert_task_run(
                session_id="dup_task",
                task_name="task",
                cwd=tmp_path,
                db_rel_path=DB_REL,
            )

    def test_get_missing_task_run_returns_none(self, tmp_path: Path) -> None:
        assert get_task_run("non_existent", cwd=tmp_path, db_rel_path=DB_REL) is None

    def test_update_task_run_status(self, tmp_path: Path) -> None:
        insert_task_run(
            session_id="task_to_update",
            task_name="task",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        updated = update_task_run_status(
            session_id="task_to_update",
            status=RunStatus.COMPLETED,
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        assert updated is not None
        assert updated.status is RunStatus.COMPLETED
        assert updated.completed_at is not None
        assert updated.error_message is None

    def test_update_missing_task_run_returns_none(self, tmp_path: Path) -> None:
        assert (
            update_task_run_status(
                session_id="missing",
                status=RunStatus.COMPLETED,
                cwd=tmp_path,
                db_rel_path=DB_REL,
            )
            is None
        )

    def test_invalid_task_status_raises_value_error(self, tmp_path: Path) -> None:
        insert_task_run(
            session_id="task_invalid_status",
            task_name="task",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        with pytest.raises(ValueError, match="constraint"):
            update_task_run_status(
                session_id="task_invalid_status",
                status="invalid_status",  # type: ignore[arg-type]
                cwd=tmp_path,
                db_rel_path=DB_REL,
            )

    def test_list_task_runs(self, tmp_path: Path) -> None:
        insert_task_run(
            session_id="t_1",
            task_name="t1",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )
        insert_task_run(
            session_id="t_2",
            task_name="t2",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        runs = list_task_runs(cwd=tmp_path, db_rel_path=DB_REL)
        assert len(runs) == 2
        assert {r.session_id for r in runs} == {"t_1", "t_2"}
