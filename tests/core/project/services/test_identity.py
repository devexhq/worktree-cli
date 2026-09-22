"""Unit tests for worktree.core.project.services.identity."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from worktree.common.lock import LockTimeoutError
from worktree.core.project.models import (
    ProjectIdentity,
    ProjectIdentityErrorType,
    ProjectIdentityLoadStatus,
    ProjectIdentitySaveStatus,
)
from worktree.core.project.services import identity as identity_service
from worktree.core.project.services.identity import (
    generate_project_identity,
    load_project_identity,
    save_project_identity,
)

UTC_TIMESTAMP = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class ProjectIdentityServiceTests:
    """Unit tests for project identity services."""

    @freeze_time(UTC_TIMESTAMP)
    def test_generate_project_identity_with_explicit_values_returns_utc_identity(self) -> None:
        """Explicit project values are retained with the frozen UTC creation timestamp."""
        identity = generate_project_identity("project-624", "Project 624")

        assert identity.id == "project-624"
        assert identity.display_name == "Project 624"
        assert identity.created_at == UTC_TIMESTAMP

    def test_generate_project_identity_without_id_uses_generated_slug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An omitted project ID uses the generated slug collaborator and a UTC timestamp."""
        monkeypatch.setattr(identity_service, "generate_slug", lambda: "calm-otter")

        identity = generate_project_identity(display_name="Generated Project")

        assert identity.id == "calm-otter"
        assert identity.created_at.utcoffset() == UTC_TIMESTAMP.utcoffset()

    def test_load_project_identity_valid_json_returns_ok_result(self, tmp_path: Path) -> None:
        """Valid serialized JSON returns the complete persisted identity."""
        path = tmp_path / "project.json"
        identity = ProjectIdentity(id="project-624", display_name="Project 624", created_at=UTC_TIMESTAMP)
        path.write_text(identity.model_dump_json(), encoding="utf-8")

        result = load_project_identity(path)

        assert result.status == ProjectIdentityLoadStatus.OK
        assert result.path == path
        assert result.identity == identity
        assert result.error is None

    def test_load_project_identity_missing_path_returns_not_found_result(self, tmp_path: Path) -> None:
        """An absent project identity file returns NOT_FOUND with its requested path."""
        path = tmp_path / "project.json"

        result = load_project_identity(path)

        assert result.status == ProjectIdentityLoadStatus.NOT_FOUND
        assert result.path == path
        assert result.error is not None
        assert result.error.error_type == ProjectIdentityErrorType.NOT_FOUND
        assert result.error.path == str(path)
        assert result.errors == [result.error.message]

    @pytest.mark.parametrize(
        "contents",
        [
            pytest.param("{not-json", id="malformed_json"),
            pytest.param('{"id": "Bad", "created_at": "2026-01-02T03:04:05Z"}', id="invalid_identity"),
        ],
    )
    def test_load_project_identity_invalid_content_returns_invalid_schema_result(
        self, tmp_path: Path, contents: str
    ) -> None:
        """Malformed or schema-invalid JSON returns INVALID_SCHEMA with its requested path."""
        path = tmp_path / "project.json"
        path.write_text(contents, encoding="utf-8")

        result = load_project_identity(path)

        assert result.status == ProjectIdentityLoadStatus.INVALID_SCHEMA
        assert result.path == path
        assert result.error is not None
        assert result.error.error_type == ProjectIdentityErrorType.INVALID_SCHEMA
        assert result.error.path == str(path)
        assert result.errors == [result.error.message]

    def test_load_project_identity_unreadable_path_returns_unreadable_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A read OSError returns UNREADABLE with its requested path."""
        path = tmp_path / "project.json"
        path.write_text("{}", encoding="utf-8")

        def raise_read_error(_path: Path, *args: object, **kwargs: object) -> str:
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "read_text", raise_read_error)

        result = load_project_identity(path)

        assert result.status == ProjectIdentityLoadStatus.UNREADABLE
        assert result.path == path
        assert result.error is not None
        assert result.error.error_type == ProjectIdentityErrorType.UNREADABLE
        assert result.error.path == str(path)
        assert result.errors == [result.error.message]

    def test_save_project_identity_writes_indented_json_without_temp_sibling(self, tmp_path: Path) -> None:
        """A valid identity is persisted as indented JSON without a temporary sibling."""
        path = tmp_path / "project.json"
        identity = ProjectIdentity(id="project-624", display_name="Project 624", created_at=UTC_TIMESTAMP)

        result = save_project_identity(path, identity)
        contents = path.read_text(encoding="utf-8")

        assert result.status == ProjectIdentitySaveStatus.OK
        assert result.path == path
        assert json.loads(contents) == identity.model_dump(mode="json")
        assert contents.startswith("{\n  ")
        assert contents.endswith("\n")
        assert not (tmp_path / "project.json.tmp").exists()

    def test_save_project_identity_atomic_write_oserror_returns_write_failed_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An atomic-write OSError returns WRITE_FAILED with its requested path."""
        path = tmp_path / "project.json"
        identity = ProjectIdentity(id="project-624", display_name="Project 624", created_at=UTC_TIMESTAMP)

        def raise_write_error(_path: Path, _data: dict[str, object]) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(identity_service.Filesystem, "atomic_write_json", raise_write_error)

        result = save_project_identity(path, identity)

        assert result.status == ProjectIdentitySaveStatus.WRITE_FAILED
        assert result.path == path
        assert result.error is not None
        assert result.error.error_type == ProjectIdentityErrorType.WRITE_FAILED
        assert result.error.path == str(path)
        assert "disk full" in result.error.message
        assert result.errors == [result.error.message]

    def test_save_project_identity_lock_timeout_returns_locked_result(self, tmp_path: Path) -> None:
        """A workspace lock timeout returns LOCKED with its requested path."""
        path = tmp_path / "project.json"
        identity = ProjectIdentity(id="project-624", display_name="Project 624", created_at=UTC_TIMESTAMP)

        with patch(
            "worktree.core.project.services.identity.WorkspaceLock.__enter__",
            side_effect=LockTimeoutError("lock held"),
        ):
            result = save_project_identity(path, identity)

        assert result.status == ProjectIdentitySaveStatus.LOCKED
        assert result.path == path
        assert result.error is not None
        assert result.error.error_type == ProjectIdentityErrorType.LOCKED
        assert result.error.path == str(path)
        assert "lock held" in result.error.message
        assert result.errors == [result.error.message]
