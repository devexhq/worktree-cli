"""Unit tests for SQLModel record models and Alembic metadata registration."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlmodel import SQLModel

from tests.helpers import FileSystem
from worktree.core.db import (
    BlueprintKind,
    CatalogItemType,
    CatalogRecord,
    RunRecord,
    RunStatus,
    SandboxRecord,
    SandboxStatus,
    WorkflowCostRecord,
)


class TestSQLModelRecords:
    """Tests verifying SQLModel table models, field coercions, and validation."""

    def test_models_subclass_sqlmodel_and_register_tables(self) -> None:
        """Verify all record classes are SQLModel tables and registered in metadata."""
        for model in (SandboxRecord, CatalogRecord, RunRecord, WorkflowCostRecord):
            assert issubclass(model, SQLModel)
            assert getattr(model, "__table__", None) is not None

        tables = SQLModel.metadata.tables
        assert "sandboxes" in tables
        assert "catalog" in tables
        assert "runs" in tables
        assert "workflow_costs" in tables

    def test_sandbox_record_field_validation_and_path_coercion(self) -> None:
        """Verify SandboxRecord coerces str paths to Path and supports path property."""
        record_from_str = SandboxRecord(
            id="sbx_1",
            name="test-sandbox",
            branch_name="feature/test",
            base_commit="abc1234",
            sandbox_path="/tmp/sbx_1",
            status=SandboxStatus.ACTIVE,
        )
        assert isinstance(record_from_str.sandbox_path, Path)
        assert record_from_str.sandbox_path == Path("/tmp/sbx_1")
        assert record_from_str.path == Path("/tmp/sbx_1")
        assert str(record_from_str.sandbox_path) == "/tmp/sbx_1"
        assert record_from_str.created_at
        assert record_from_str.updated_at

        record_from_path = SandboxRecord(
            id="sbx_2",
            branch_name="feature/test2",
            base_commit="def5678",
            sandbox_path=Path("/tmp/sbx_2"),
            status="merged",
        )
        assert isinstance(record_from_path.sandbox_path, Path)
        assert record_from_path.status == SandboxStatus.MERGED
        assert record_from_path.name is None

    def test_catalog_record_field_validation_and_path_coercion(self) -> None:
        """Verify CatalogRecord coerces str paths to Path and supports enum types."""
        record = CatalogRecord(
            sha="sha_12345",
            item_type=CatalogItemType.TASK,
            name="my-task",
            path="tasks/my-task.yml",
            checksum="chk_123",
        )
        assert isinstance(record.path, Path)
        assert record.path == Path("tasks/my-task.yml")
        assert record.item_type == CatalogItemType.TASK
        assert record.id is None
        assert record.created_at
        assert record.updated_at

        record_with_id = CatalogRecord(
            id=42,
            sha="sha_67890",
            item_type="workflow",
            name="my-wf",
            path=Path("workflows/my-wf.yml"),
            checksum="chk_456",
        )
        assert record_with_id.id == 42
        assert record_with_id.item_type == CatalogItemType.WORKFLOW
        assert isinstance(record_with_id.path, Path)

    def test_run_record_defaults_and_validation(self) -> None:
        """Verify RunRecord default values, status, and kind enums."""
        record = RunRecord(
            session_id="session_100",
            blueprint_name="build-flow",
            kind=BlueprintKind.WORKFLOW,
        )
        assert record.id is None
        assert record.session_id == "session_100"
        assert record.blueprint_name == "build-flow"
        assert record.kind == BlueprintKind.WORKFLOW
        assert record.branch_name == ""
        assert record.status == RunStatus.RUNNING
        assert record.started_at
        assert record.completed_at is None
        assert record.error_message is None
        assert record.checkpoint_json is None

    def test_workflow_cost_record_defaults_and_validation(self) -> None:
        """Verify WorkflowCostRecord defaults for token counts and cost."""
        record = WorkflowCostRecord(
            session_id="session_200",
            branch_name="main",
            model_id="claude-3-7-sonnet",
        )
        assert record.id is None
        assert record.session_id == "session_200"
        assert record.branch_name == "main"
        assert record.model_id == "claude-3-7-sonnet"
        assert record.prompt_tokens == 0
        assert record.completion_tokens == 0
        assert record.total_tokens == 0
        assert record.estimated_usd_cost == 0.0
        assert record.created_at

    def test_model_extra_fields_forbidden(self) -> None:
        """Verify extra unexpected fields are rejected on model validation."""
        with pytest.raises(ValidationError):
            SandboxRecord.model_validate(
                {
                    "id": "sbx_extra",
                    "branch_name": "b",
                    "base_commit": "c",
                    "sandbox_path": "/tmp/x",
                    "status": "active",
                    "unknown_field": "disallowed",
                }
            )


class TestAlembicMigrations:
    """Tests verifying embedded Alembic migrations and schema application."""

    def test_alembic_upgrade_and_downgrade(self, fs: FileSystem) -> None:
        """Verify running Alembic upgrade head creates all tables and downgrade drops them."""
        db_path = fs.base_path / "test_migration.db"
        alembic_dir = Path(__file__).resolve().parents[2] / "src" / "worktree" / "core" / "db" / "alembic"

        config = Config()
        config.set_main_option("script_location", str(alembic_dir))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

        command.upgrade(config, "head")

        with sqlite3.connect(db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}

        assert "sandboxes" in tables
        assert "catalog" in tables
        assert "runs" in tables
        assert "workflow_costs" in tables
        assert "alembic_version" in tables

        assert "idx_sandboxes_status" in indexes
        assert "idx_catalog_sha" in indexes
        assert "idx_catalog_type" in indexes
        assert "idx_catalog_path" in indexes
        assert "idx_runs_session" in indexes
        assert "idx_runs_status" in indexes
        assert "idx_runs_started" in indexes
        assert "idx_workflow_costs_session" in indexes
        assert "idx_workflow_costs_created" in indexes

        command.downgrade(config, "base")

        with sqlite3.connect(db_path) as conn:
            tables_after_downgrade = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }

        assert "sandboxes" not in tables_after_downgrade
        assert "catalog" not in tables_after_downgrade
        assert "runs" not in tables_after_downgrade
        assert "workflow_costs" not in tables_after_downgrade
