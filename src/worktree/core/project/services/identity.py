"""Project identity creation and persistence services."""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from worktree.common.filesystem.facade import Filesystem
from worktree.common.lock import LockTimeoutError, WorkspaceLock
from worktree.core.project.models import (
    ProjectIdentity,
    ProjectIdentityError,
    ProjectIdentityErrorType,
    ProjectIdentityLoadResult,
    ProjectIdentityLoadStatus,
    ProjectIdentitySaveResult,
    ProjectIdentitySaveStatus,
)
from worktree.core.project.services.slug import generate_slug


def generate_project_identity(
    project_id: str | None = None,
    display_name: str | None = None,
) -> ProjectIdentity:
    """Create a validated project identity using a supplied or generated identifier."""
    return ProjectIdentity(
        id=generate_slug() if project_id is None else project_id,
        display_name=display_name,
        created_at=datetime.now(UTC),
    )


def load_project_identity(path: Path) -> ProjectIdentityLoadResult:
    """Load a JSON project identity or return a classified persistence result."""
    if not path.exists():
        message = f"Project identity file not found at '{path}' (PROJECT_IDENTITY_NOT_FOUND)."
        return ProjectIdentityLoadResult(
            status=ProjectIdentityLoadStatus.NOT_FOUND,
            path=path,
            error=ProjectIdentityError(
                error_type=ProjectIdentityErrorType.NOT_FOUND,
                message=message,
                path=str(path),
            ),
            errors=[message],
        )

    try:
        identity = ProjectIdentity.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        message = f"Project identity at '{path}' is invalid: {exc} (PROJECT_IDENTITY_INVALID_SCHEMA)."
        return ProjectIdentityLoadResult(
            status=ProjectIdentityLoadStatus.INVALID_SCHEMA,
            path=path,
            error=ProjectIdentityError(
                error_type=ProjectIdentityErrorType.INVALID_SCHEMA,
                message=message,
                path=str(path),
            ),
            errors=[message],
        )
    except OSError as exc:
        message = f"Unable to read project identity at '{path}': {exc} (PROJECT_IDENTITY_UNREADABLE)."
        return ProjectIdentityLoadResult(
            status=ProjectIdentityLoadStatus.UNREADABLE,
            path=path,
            error=ProjectIdentityError(
                error_type=ProjectIdentityErrorType.UNREADABLE,
                message=message,
                path=str(path),
            ),
            errors=[message],
        )

    return ProjectIdentityLoadResult(
        status=ProjectIdentityLoadStatus.OK,
        path=path,
        identity=identity,
    )


def save_project_identity(path: Path, identity: ProjectIdentity) -> ProjectIdentitySaveResult:
    """Persist a project identity atomically or return a classified write result."""
    try:
        with WorkspaceLock(path.parent):
            Filesystem.atomic_write_json(path, identity.model_dump(mode="json"))
    except LockTimeoutError as exc:
        message = f"Unable to acquire project identity lock at '{path}': {exc} (PROJECT_IDENTITY_LOCKED)."
        return ProjectIdentitySaveResult(
            status=ProjectIdentitySaveStatus.LOCKED,
            path=path,
            error=ProjectIdentityError(
                error_type=ProjectIdentityErrorType.LOCKED,
                message=message,
                path=str(path),
            ),
            errors=[message],
        )
    except OSError as exc:
        message = f"Unable to write project identity at '{path}': {exc} (PROJECT_IDENTITY_WRITE_FAILED)."
        return ProjectIdentitySaveResult(
            status=ProjectIdentitySaveStatus.WRITE_FAILED,
            path=path,
            error=ProjectIdentityError(
                error_type=ProjectIdentityErrorType.WRITE_FAILED,
                message=message,
                path=str(path),
            ),
            errors=[message],
        )

    return ProjectIdentitySaveResult(status=ProjectIdentitySaveStatus.OK, path=path)
