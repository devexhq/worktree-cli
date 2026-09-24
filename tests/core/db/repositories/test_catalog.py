"""Contract tests for CatalogRepository project_id scoping."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from worktree.core.db.connection import get_engine
from worktree.core.db.migrations import init_database
from worktree.core.db.models import CatalogItemType
from worktree.core.db.repositories.catalog import CatalogRepository


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Path to a freshly migrated, isolated SQLite database file."""
    path = tmp_path / "worktree.db"
    init_database(db_path=path)
    return path


@pytest.fixture
def db_engine(db_path: Path) -> Engine:
    """Engine bound to the migrated database file, shared across scoped repositories."""
    return get_engine(db_path)


class CatalogRepositoryTests:
    """Contract tests proving CatalogRepository queries never cross project_id boundaries."""

    def test_upsert_allows_identical_sha_across_different_projects(self, db_path: Path, db_engine: Engine) -> None:
        """[tier-1/integration] CatalogRepository.upsert: identical sha/key/path upserted under project_id='proj-a' and project_id='proj-b' both succeed without IntegrityError."""
        repo_a = CatalogRepository(db_path=db_path, db_engine=db_engine, project_id="proj-a")
        repo_b = CatalogRepository(db_path=db_path, db_engine=db_engine, project_id="proj-b")

        record_a = repo_a.upsert(
            sha="deadbeef",
            item_type=CatalogItemType.BLUEPRINT,
            name="deploy",
            namespace=None,
            path="blueprints/deploy.yaml",
            checksum="deadbeef",
        )
        record_b = repo_b.upsert(
            sha="deadbeef",
            item_type=CatalogItemType.BLUEPRINT,
            name="deploy",
            namespace=None,
            path="blueprints/deploy.yaml",
            checksum="deadbeef",
        )

        assert record_a.project_id == "proj-a"
        assert record_b.project_id == "proj-b"

    def test_get_by_key_scopes_to_repository_project_id(self, db_path: Path, db_engine: Engine) -> None:
        """[tier-1/integration] CatalogRepository.get_by_key: record upserted under project_id='proj-a' returns None when fetched by a project_id='proj-b' repository."""
        repo_a = CatalogRepository(db_path=db_path, db_engine=db_engine, project_id="proj-a")
        repo_b = CatalogRepository(db_path=db_path, db_engine=db_engine, project_id="proj-b")
        repo_a.upsert(
            sha="deadbeef",
            item_type=CatalogItemType.BLUEPRINT,
            name="deploy",
            namespace="blueprints",
            path="blueprints/deploy.yaml",
            checksum="deadbeef",
        )

        assert repo_b.get_by_key("blueprints/deploy") is None
        assert repo_a.get_by_key("blueprints/deploy") is not None

    def test_list_scopes_to_repository_project_id(self, db_path: Path, db_engine: Engine) -> None:
        """[tier-1/integration] CatalogRepository.list: record upserted under project_id='proj-a' is absent from a project_id='proj-b' repository's list()."""
        repo_a = CatalogRepository(db_path=db_path, db_engine=db_engine, project_id="proj-a")
        repo_b = CatalogRepository(db_path=db_path, db_engine=db_engine, project_id="proj-b")
        repo_a.upsert(
            sha="deadbeef",
            item_type=CatalogItemType.BLUEPRINT,
            name="deploy",
            namespace=None,
            path="blueprints/deploy.yaml",
            checksum="deadbeef",
        )

        assert repo_b.list() == []
        assert len(repo_a.list()) == 1
