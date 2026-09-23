"""Diagnostic check validating write access across configured workspace paths."""

from __future__ import annotations

import uuid
from pathlib import Path

from worktree.core.config.models import PathsConfig
from worktree.core.doctor.models import CheckCategory, CheckStatus, DiagnosticCheckResult, DoctorContext
from worktree.core.project.services.storage import resolve_project_filesystem_paths


class FilesystemWritableCheck:
    """Diagnostic check validating write access across configured workspace paths."""

    check_id: str = "filesystem.writable"
    name: str = "Filesystem Writable Check"
    category: CheckCategory = CheckCategory.FILESYSTEM

    def execute(self, context: DoctorContext) -> DiagnosticCheckResult:
        """Probe-write every PathsConfig-declared directory (plus sandboxes) under context.cwd."""
        paths = context.config.paths if context.config is not None else PathsConfig()
        targets = _target_paths(context.cwd, paths)

        verified_paths: list[str] = []
        unwritable_paths: list[str] = []
        for path in targets.values():
            if _is_path_writable(path):
                verified_paths.append(str(path))
            else:
                unwritable_paths.append(str(path))

        if unwritable_paths:
            message = f"{len(unwritable_paths)} configured path(s) are not writable."
            return DiagnosticCheckResult(
                check_id=self.check_id,
                name=self.name,
                category=self.category,
                status=CheckStatus.FAILED,
                message=message,
                details={"unwritable_paths": unwritable_paths},
                duration_ms=0.0,
                error_code="DOCTOR_FS_UNWRITABLE",
                errors=[message],
                warnings=[],
                fixes=[],
            )

        return DiagnosticCheckResult(
            check_id=self.check_id,
            name=self.name,
            category=self.category,
            status=CheckStatus.OK,
            message="All configured workspace paths are writable.",
            details={"verified_paths": verified_paths},
            duration_ms=0.0,
            error_code=None,
            errors=[],
            warnings=[],
            fixes=[],
        )


def _target_paths(cwd: Path, paths: PathsConfig) -> dict[str, Path]:
    """Return the ordered label-to-directory mapping of paths to probe for write access."""
    filesystem_paths = resolve_project_filesystem_paths(cwd)
    if filesystem_paths.project_id is None:
        sessions_dir = cwd / paths.sessions_dir
        artifacts_dir = cwd / paths.artifacts_dir
    else:
        sessions_dir = filesystem_paths.sessions_dir
        artifacts_dir = filesystem_paths.artifacts_dir

    return {
        "root_dir": cwd / paths.root_dir,
        "sessions_dir": sessions_dir,
        "artifacts_dir": artifacts_dir,
        "sandboxes_dir": cwd / paths.root_dir / "sandboxes",
        "database": (cwd / paths.db_path).parent,
    }


def _is_path_writable(path: Path) -> bool:
    """Create path if missing and verify a unique probe file can be written and removed."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    probe_path = path / f".probe-{uuid.uuid4()}.tmp"
    try:
        probe_path.write_text("", encoding="utf-8")
    except OSError:
        return False
    finally:
        probe_path.unlink(missing_ok=True)

    return True
