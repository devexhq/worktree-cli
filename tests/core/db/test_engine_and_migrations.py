"""Tests for SQLite engine factory, WAL pragmas, programmatic Alembic migrations, and BaseRepository."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import select

from tests.helpers import FileSystem
from worktree.core.db import (
    INITIAL_SCHEMA_REVISION,
    BaseRepository,
    BlueprintKind,
    RunRecord,
    RunStatus,
    SandboxRecord,
    SandboxStatus,
    get_engine,
    get_session,
    init_database,
    resolve_db_path,
    sqlite_url,
)


class TestEngineAndPragmas:
    """Tests for get_engine, SQLite PRAGMA configuration, and get_session."""

    def test_sqlite_url_helper(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        assert sqlite_url(db_path) == f"sqlite:///{db_path}"

    def test_get_engine_creates_parent_dir_and_sets_pragmas(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "test.db"
        assert not db_path.parent.exists()

        engine = get_engine(db_path)
        assert db_path.parent.is_dir()

        with engine.connect() as conn:
            journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
            busy_timeout = conn.execute(text("PRAGMA busy_timeout;")).scalar()
            foreign_keys = conn.execute(text("PRAGMA foreign_keys;")).scalar()

        assert str(journal_mode).lower() == "wal"
        assert busy_timeout == 5000
        assert foreign_keys == 1

    def test_get_session_context_manager(self, tmp_path: Path) -> None:
        db_path = tmp_path / "session_test.db"
        init_database(db_path=db_path)
        engine = get_engine(db_path)

        with get_session(engine) as session:
            record = RunRecord(
                session_id="s_test",
                blueprint_name="bp_test",
                kind=BlueprintKind.TASK,
                status=RunStatus.RUNNING,
            )
            session.add(record)
            session.commit()

        with get_session(engine) as session:
            loaded = session.exec(select(RunRecord).where(RunRecord.session_id == "s_test")).first()
            assert loaded is not None
            assert loaded.blueprint_name == "bp_test"


class TestProgrammaticMigrations:
    """Tests for programmatic Alembic upgrades."""

    def test_init_database_creates_all_tables_and_alembic_version(self, tmp_path: Path) -> None:
        db_path = tmp_path / "fresh.db"
        result_path = init_database(db_path=db_path)
        assert result_path == db_path
        assert db_path.is_file()

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute("SELECT version_num FROM alembic_version")
            version_row = cursor.fetchone()
        finally:
            conn.close()

        assert version_row is not None
        assert version_row[0] == INITIAL_SCHEMA_REVISION

    def test_resolve_db_path_helper(self, tmp_path: Path) -> None:
        resolved = resolve_db_path(path=tmp_path, db_rel_path=".custom/my.db")
        assert resolved == (tmp_path / ".custom/my.db").resolve()
        assert resolved.parent.is_dir()


class TestBaseRepository:
    """Tests for BaseRepository lazy initialization, session lifecycle, and CRUD helpers."""

    def test_base_repository_lazy_init_and_session(self, fs: FileSystem) -> None:
        repo = BaseRepository(path=fs.base_path, db_rel_path=".worktree/custom.db")

        with repo.session() as session:
            sandbox = SandboxRecord(
                id="sb_base_repo",
                branch_name="feature/repo",
                base_commit="commit_abc",
                sandbox_path=fs.base_path / "sandboxes" / "sb_base_repo",
                status=SandboxStatus.ACTIVE,
            )
            session.add(sandbox)
            session.commit()

        with repo.session() as session:
            loaded = session.exec(select(SandboxRecord).where(SandboxRecord.id == "sb_base_repo")).first()
            assert loaded is not None
            assert loaded.branch_name == "feature/repo"
            assert loaded.sandbox_path == fs.base_path / "sandboxes" / "sb_base_repo"

    def test_base_repository_explicit_init_db(self, fs: FileSystem) -> None:
        repo = BaseRepository(path=fs.base_path, auto_init=False)
        db_path = repo.init_db()
        assert db_path.is_file()

    def test_base_repository_commit_and_delete_where(self, fs: FileSystem) -> None:
        repo = BaseRepository(path=fs.base_path, db_rel_path=".worktree/helpers.db")

        record = SandboxRecord(
            id="sb_helper",
            branch_name="feat/helper",
            base_commit="abc",
            sandbox_path=fs.base_path / "sb_helper",
            status=SandboxStatus.ACTIVE,
        )

        with repo.session() as session:
            committed = repo._commit(session, record, "Failed to commit record")
            assert committed.id == "sb_helper"

        # Duplicate commit should rollback and raise ValueError
        dup = SandboxRecord(
            id="sb_helper",
            branch_name="feat/helper2",
            base_commit="def",
            sandbox_path=fs.base_path / "sb_helper2",
            status=SandboxStatus.ACTIVE,
        )
        with repo.session() as session:
            with pytest.raises(ValueError, match="Duplicate sandbox"):
                repo._commit(session, dup, "Duplicate sandbox")

        # Delete where matches
        with repo.session() as session:
            stmt = select(SandboxRecord).where(SandboxRecord.id == "sb_helper")
            assert repo._delete_where(session, stmt) is True

        # Delete where missing
        with repo.session() as session:
            stmt = select(SandboxRecord).where(SandboxRecord.id == "sb_helper")
            assert repo._delete_where(session, stmt) is False
