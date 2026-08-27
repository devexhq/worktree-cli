"""Tests for SQLite database tables, BaseRepository, repository classes, and WorktreeDb facade."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.db import (
    BaseRepository,
    BlueprintKind,
    CatalogItemType,
    CatalogRecord,
    RunRecord,
    SandboxRecord,
    WorktreeDb,
    get_db_connection,
    init_database,
)
from worktree.core.db.models import SandboxStatus

DB_REL = ".worktree/data.db"


class TestDatabaseMigrations:
    """Tests for database initialization and schema creation."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path, db_rel_path=DB_REL)

    def test_init_creates_database_file(self, fs: FileSystem) -> None:
        db_path = init_database(path=fs.base_path, db_rel_path=DB_REL)
        assert db_path.is_file()
        assert self.db.runs.list() == []

    def test_init_is_idempotent(self, fs: FileSystem) -> None:
        path1 = init_database(path=fs.base_path, db_rel_path=DB_REL)
        path2 = init_database(path=fs.base_path, db_rel_path=DB_REL)
        assert path1 == path2
        assert path1.is_file()

    def test_get_db_connection_lifecycle(self, fs: FileSystem) -> None:
        db_path = init_database(path=fs.base_path, db_rel_path=DB_REL)
        with get_db_connection(db_path) as conn:
            cursor = conn.execute("SELECT 1 AS num")
            row = cursor.fetchone()
            assert row is not None
            assert row["num"] == 1

    def test_get_db_connection_rollback_on_error(self, fs: FileSystem) -> None:
        db_path = init_database(path=fs.base_path, db_rel_path=DB_REL)
        with pytest.raises(RuntimeError, match="simulated db error"):
            with get_db_connection(db_path) as conn:
                conn.execute("SELECT 1")
                raise RuntimeError("simulated db error")


class TestBaseRepository:
    """Tests for BaseRepository core path resolution, init_db, and session lifecycle."""

    def test_db_path_resolution(self, fs: FileSystem) -> None:
        repo = BaseRepository(path=fs.base_path, db_rel_path=DB_REL)
        assert repo.db_path == fs.base_path / DB_REL

        custom_path = fs.base_path / "custom.db"
        repo_custom = BaseRepository(db_path=custom_path)
        assert repo_custom.db_path == custom_path

    def test_init_db_creates_file(self, fs: FileSystem) -> None:
        repo = BaseRepository(path=fs.base_path, db_rel_path=DB_REL)
        path = repo.init_db()
        assert path.is_file()

    def test_session_auto_inits_db(self, fs: FileSystem) -> None:
        repo = BaseRepository(path=fs.base_path, db_rel_path=DB_REL)
        with repo.session() as session:
            assert session is not None
        assert repo.db_path.is_file()

    def test_custom_db_engine(self, fs: FileSystem) -> None:
        custom_engine = BaseRepository(path=fs.base_path, db_rel_path=DB_REL).db_engine
        repo = BaseRepository(path=fs.base_path, db_engine=custom_engine)
        assert repo.db_engine is custom_engine
        assert repo.engine is custom_engine


class TestSandboxesRepository:
    """Tests for SandboxesRepository CRUD methods."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path, db_rel_path=DB_REL)

    def test_create_and_get(self, fs: FileSystem) -> None:
        sb = self.db.sandboxes.create(
            id="sb-001",
            branch_name="feat/branch",
            base_commit="abc123",
            sandbox_path=fs.base_path / "sb-001",
        )

        assert isinstance(sb, SandboxRecord)
        assert sb.id == "sb-001"
        assert sb.branch_name == "feat/branch"
        assert sb.base_commit == "abc123"
        assert sb.sandbox_path == fs.base_path / "sb-001"
        assert sb.status == SandboxStatus.ACTIVE
        assert sb.name is None
        assert sb.created_at
        assert sb.updated_at

        fetched = self.db.sandboxes.get("sb-001")
        assert fetched == sb

    def test_create_with_name(self, fs: FileSystem) -> None:
        sb = self.db.sandboxes.create(
            id="sb-named",
            branch_name="feat/named",
            base_commit="def456",
            sandbox_path=fs.base_path / "sb-named",
            name="my-sandbox",
        )
        assert sb.name == "my-sandbox"

    def test_create_duplicate_raises_value_error(self, fs: FileSystem) -> None:
        self.db.sandboxes.create(id="dup-id", branch_name="b", base_commit="c", sandbox_path=fs.base_path / "dup")
        with pytest.raises(ValueError, match="dup-id"):
            self.db.sandboxes.create(
                id="dup-id", branch_name="b2", base_commit="c2", sandbox_path=fs.base_path / "dup2"
            )

    def test_get_missing_returns_none(self, fs: FileSystem) -> None:
        assert self.db.sandboxes.get("does-not-exist") is None

    def test_list_unfiltered_and_filtered(self, fs: FileSystem) -> None:
        self.db.sandboxes.create(id="a", branch_name="b", base_commit="c", sandbox_path=fs.base_path / "a")
        self.db.sandboxes.create(id="b", branch_name="b2", base_commit="c2", sandbox_path=fs.base_path / "b")
        self.db.sandboxes.update_status("b", SandboxStatus.MERGED)

        all_rows = self.db.sandboxes.list()
        assert len(all_rows) == 2

        active = self.db.sandboxes.list(status=SandboxStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].id == "a"

        merged = self.db.sandboxes.list(status=SandboxStatus.MERGED)
        assert len(merged) == 1
        assert merged[0].id == "b"

    def test_update_status(self, fs: FileSystem) -> None:
        sb = self.db.sandboxes.create(id="upd", branch_name="b", base_commit="c", sandbox_path=fs.base_path / "upd")
        original_updated_at = sb.updated_at

        updated = self.db.sandboxes.update_status("upd", SandboxStatus.CLEANED)
        assert updated is not None
        assert updated.status == SandboxStatus.CLEANED
        assert updated.updated_at >= original_updated_at

    def test_update_status_missing_returns_none(self, fs: FileSystem) -> None:
        assert self.db.sandboxes.update_status("ghost", SandboxStatus.CLEANED) is None

    def test_delete(self, fs: FileSystem) -> None:
        self.db.sandboxes.create(id="del-me", branch_name="b", base_commit="c", sandbox_path=fs.base_path / "del-me")

        assert self.db.sandboxes.delete("del-me") is True
        assert self.db.sandboxes.get("del-me") is None
        assert self.db.sandboxes.delete("del-me") is False

    def test_reconcile_stale_active_all(self, fs: FileSystem) -> None:
        active_existing_dir = fs.base_path / "existing-dir"
        active_existing_dir.mkdir(parents=True, exist_ok=True)
        active_missing_dir1 = fs.base_path / "missing-dir-1"
        active_missing_dir2 = fs.base_path / "missing-dir-2"

        self.db.sandboxes.create(id="sb-alive", branch_name="b1", base_commit="c1", sandbox_path=active_existing_dir)
        self.db.sandboxes.create(id="sb-stale", branch_name="b2", base_commit="c2", sandbox_path=active_missing_dir1)
        self.db.sandboxes.create(id="sb-cleaned", branch_name="b3", base_commit="c3", sandbox_path=active_missing_dir2)
        self.db.sandboxes.update_status("sb-cleaned", SandboxStatus.CLEANED)

        reconciled = self.db.sandboxes.reconcile_stale_active()
        assert len(reconciled) == 1
        assert reconciled[0].id == "sb-stale"
        assert reconciled[0].status == SandboxStatus.CLEANED

        alive = self.db.sandboxes.get("sb-alive")
        assert alive is not None
        assert alive.status == SandboxStatus.ACTIVE

        stale = self.db.sandboxes.get("sb-stale")
        assert stale is not None
        assert stale.status == SandboxStatus.CLEANED

    def test_reconcile_stale_active_by_id(self, fs: FileSystem) -> None:
        active_missing_dir1 = fs.base_path / "missing-dir-1"
        active_missing_dir2 = fs.base_path / "missing-dir-2"
        self.db.sandboxes.create(id="sb-target", branch_name="b1", base_commit="c1", sandbox_path=active_missing_dir1)
        self.db.sandboxes.create(id="sb-other", branch_name="b2", base_commit="c2", sandbox_path=active_missing_dir2)

        reconciled = self.db.sandboxes.reconcile_stale_active(id="sb-target")
        assert len(reconciled) == 1
        assert reconciled[0].id == "sb-target"

        target = self.db.sandboxes.get("sb-target")
        assert target is not None
        assert target.status == SandboxStatus.CLEANED

        other = self.db.sandboxes.get("sb-other")
        assert other is not None
        assert other.status == SandboxStatus.ACTIVE


class TestCatalogRepository:
    """Tests for CatalogRepository repository methods."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path, db_rel_path=DB_REL)

    def test_upsert_insert_and_get_by_sha_and_name(self, fs: FileSystem) -> None:
        path = Path(".worktree/catalog/workflow_a.yaml")
        rec = self.db.catalog.upsert(
            sha="workflow_1234567",
            item_type=CatalogItemType.WORKFLOW,
            name="workflow_a",
            path=path,
            checksum="hash1",
        )

        assert isinstance(rec, CatalogRecord)
        assert rec.id == 1
        assert rec.sha == "workflow_1234567"
        assert rec.item_type == CatalogItemType.WORKFLOW
        assert rec.name == "workflow_a"
        assert rec.path == path
        assert rec.checksum == "hash1"
        assert rec.created_at
        assert rec.updated_at

        by_sha = self.db.catalog.get_by_sha("workflow_1234567")
        assert by_sha == rec

        by_name = self.db.catalog.get_by_name("workflow_a")
        assert by_name == rec

        by_name_and_type = self.db.catalog.get_by_name(
            "workflow_a",
            item_type=CatalogItemType.WORKFLOW,
        )
        assert by_name_and_type == rec

        by_path = self.db.catalog.get_by_path(path)
        assert by_path == rec

        by_str_path = self.db.catalog.get_by_path(str(path))
        assert by_str_path == rec

    def test_upsert_update_preserves_id_and_updates_fields(self, fs: FileSystem) -> None:
        path = Path(".worktree/catalog/task_b.yaml")
        first = self.db.catalog.upsert(
            sha="task_1111111",
            item_type=CatalogItemType.TASK,
            name="task_b",
            path=path,
            checksum="chk1",
        )
        first_id = first.id
        first_created_at = first.created_at

        second = self.db.catalog.upsert(
            sha="task_2222222",
            item_type=CatalogItemType.TASK,
            name="task_b_v2",
            path=path,
            checksum="chk2",
        )

        assert second.id == first_id
        assert second.sha == "task_2222222"
        assert second.name == "task_b_v2"
        assert second.path == path
        assert second.checksum == "chk2"
        assert second.created_at == first_created_at

    def test_get_missing_catalog_item_returns_none(self, fs: FileSystem) -> None:
        assert self.db.catalog.get_by_sha("missing") is None
        assert self.db.catalog.get_by_name("missing_name") is None
        assert self.db.catalog.get_by_path("missing_path.yaml") is None

    def test_list_catalog_items_filtering(self, fs: FileSystem) -> None:
        self.db.catalog.upsert(
            sha="w1", item_type=CatalogItemType.WORKFLOW, name="wf1", path=Path("w1.yaml"), checksum="c1"
        )
        self.db.catalog.upsert(
            sha="t1", item_type=CatalogItemType.TASK, name="task1", path=Path("t1.yaml"), checksum="c2"
        )
        self.db.catalog.upsert(
            sha="s1", item_type=CatalogItemType.STEP, name="step1", path=Path("s1.yaml"), checksum="c3"
        )

        all_items = self.db.catalog.list()
        assert len(all_items) == 3

        workflows = self.db.catalog.list(item_type=CatalogItemType.WORKFLOW)
        assert len(workflows) == 1
        assert workflows[0].sha == "w1"

        steps = self.db.catalog.list(item_type="step")
        assert len(steps) == 1
        assert steps[0].sha == "s1"

    def test_list_by_name(self, fs: FileSystem) -> None:
        self.db.catalog.upsert(
            sha="n1", item_type=CatalogItemType.WORKFLOW, name="shared", path=Path("a/shared.yaml"), checksum="c1"
        )
        self.db.catalog.upsert(
            sha="n2", item_type=CatalogItemType.TASK, name="shared", path=Path("b/shared.yaml"), checksum="c2"
        )

        all_shared = self.db.catalog.list_by_name("shared")
        assert len(all_shared) == 2

        wf_shared = self.db.catalog.list_by_name("shared", item_type=CatalogItemType.WORKFLOW)
        assert len(wf_shared) == 1
        assert wf_shared[0].sha == "n1"

    def test_invalid_catalog_item_type_raises_value_error(self, fs: FileSystem) -> None:
        with pytest.raises(ValueError, match="constraint"):
            self.db.catalog.upsert(
                sha="invalid",
                item_type="invalid_type",  # pyright: ignore[reportArgumentType]
                name="invalid",
                path=Path("invalid.yaml"),
                checksum="c",
            )

        with pytest.raises(ValueError, match="constraint"):
            self.db.catalog.list(item_type="invalid_type")

        with pytest.raises(ValueError, match="constraint"):
            self.db.catalog.list_by_name("name", item_type="invalid_type")

        with pytest.raises(ValueError, match="constraint"):
            self.db.catalog.get_by_name("name", item_type="invalid_type")

    def test_delete_catalog_item(self, fs: FileSystem) -> None:
        self.db.catalog.upsert(
            sha="to_delete",
            item_type=CatalogItemType.WORKFLOW,
            name="delete_item",
            path=Path("delete.yaml"),
            checksum="c_del",
        )

        assert self.db.catalog.delete("to_delete") is True
        assert self.db.catalog.get_by_sha("to_delete") is None
        assert self.db.catalog.delete("to_delete") is False


class TestWorktreeDbFacade:
    """Tests for WorktreeDb unified facade."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path, db_rel_path=DB_REL)

    def test_facade_sub_repository_access(self, fs: FileSystem) -> None:
        self.db.init_db()

        assert self.db.sandboxes.db_engine is self.db.db_engine
        assert self.db.runs.db_engine is self.db.db_engine
        assert self.db.catalog.db_engine is self.db.db_engine
        assert self.db.costs.db_engine is self.db.db_engine
        assert self.db.engine is self.db.db_engine

        sb = self.db.sandboxes.create(
            id="sb_facade",
            branch_name="feat/facade",
            base_commit="abc",
            sandbox_path=fs.base_path / "sb_facade",
        )
        assert self.db.sandboxes.get("sb_facade") == sb

        run = self.db.runs.create(
            session_id="run_facade",
            blueprint_name="demo",
            kind=BlueprintKind.WORKFLOW,
            branch_name="b",
        )
        assert isinstance(run, RunRecord)
        assert self.db.runs.get("run_facade") == run

        cat = self.db.catalog.upsert(
            sha="c_facade",
            item_type=CatalogItemType.WORKFLOW,
            name="wf_cat",
            path=Path("wf_cat.yaml"),
            checksum="c",
        )
        assert self.db.catalog.get_by_sha("c_facade") == cat

        cost_id = self.db.costs.record_token_usage(
            session_id="run_facade",
            branch_name="b",
            model_id="gpt-4o",
            prompt_tokens=10,
            completion_tokens=20,
            estimated_usd_cost=0.005,
        )
        assert cost_id is not None
        totals = self.db.costs.get_session_total_cost("run_facade")
        assert totals["total_tokens"] == 30

    def test_facade_custom_db_engine(self, fs: FileSystem) -> None:
        db1 = WorktreeDb(path=fs.base_path, db_rel_path=DB_REL)
        db2 = WorktreeDb(path=fs.base_path, db_engine=db1.db_engine)
        assert db2.db_engine is db1.db_engine
        assert db2.sandboxes.db_engine is db1.db_engine
