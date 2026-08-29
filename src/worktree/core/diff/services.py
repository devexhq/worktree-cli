"""Class-based execution service for diff inspection operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worktree.common.utils import RichOutput
from worktree.core.config.loader import load_config_result
from worktree.core.diff.models import DiffResult, DiffStatus
from worktree.core.diff.renderers import render_diff


@dataclass
class DiffService:
    """Service encapsulating session unified diff retrieval and rendering."""

    path: Path
    output: RichOutput
    session_id: str | None = None
    raw: bool = False

    def _discover_latest_session(self, sessions_dir: Path) -> Path | None:
        """Discover the most recently modified session directory under sessions_dir."""
        if not sessions_dir.is_dir():
            return None

        candidate_dirs = [entry for entry in sessions_dir.iterdir() if entry.is_dir()]
        if not candidate_dirs:
            return None

        return max(candidate_dirs, key=lambda entry: (entry.stat().st_mtime, entry.name))

    def _resolve_session_target(
        self,
        sessions_dir: Path,
    ) -> tuple[Path | None, str | None, DiffResult | None]:
        """Resolve target session directory and ID or return error DiffResult."""
        if self.session_id is not None:
            target_dir = sessions_dir / self.session_id
            if not target_dir.is_dir():
                return (
                    None,
                    None,
                    DiffResult(
                        status=DiffStatus.SESSION_NOT_FOUND,
                        session_id=self.session_id,
                        errors=[f"Session '{self.session_id}' not found under .worktree/sessions/."],
                    ),
                )
            return target_dir, self.session_id, None

        latest_dir = self._discover_latest_session(sessions_dir)
        if latest_dir is None:
            return (
                None,
                None,
                DiffResult(
                    status=DiffStatus.SESSION_NOT_FOUND,
                    errors=["No loop run sessions found."],
                ),
            )

        return latest_dir, latest_dir.name, None

    def _read_patch_artifact(self, target_dir: Path, session_id: str) -> DiffResult:
        """Read and validate diff.patch artifact within the target session directory."""
        patch_file = target_dir / "diff.patch"
        if not patch_file.is_file():
            return DiffResult(
                status=DiffStatus.DIFF_NOT_FOUND,
                session_id=session_id,
                artifact_path=patch_file,
                errors=[f"Session '{session_id}' has no diff artifact."],
            )

        try:
            diff_text = patch_file.read_text(encoding="utf-8")
        except OSError as exc:
            return DiffResult(
                status=DiffStatus.READ_FAILURE,
                session_id=session_id,
                artifact_path=patch_file,
                errors=[f"Failed to read diff artifact at '{patch_file}': {exc}"],
            )

        if not diff_text.strip():
            return DiffResult(
                status=DiffStatus.EMPTY_DIFF,
                session_id=session_id,
                artifact_path=patch_file,
                diff_text="",
            )

        return DiffResult(
            status=DiffStatus.OK,
            session_id=session_id,
            artifact_path=patch_file,
            diff_text=diff_text,
        )

    def collect(self) -> DiffResult:
        """Collect and validate the diff artifact without side effects."""
        config_load = load_config_result(path=self.path)
        if not config_load.ok or config_load.config is None:
            return DiffResult(
                status=DiffStatus.NOT_INITIALIZED,
                errors=list(config_load.errors),
            )

        sessions_dir = self.path / config_load.config.paths.sessions_dir
        target_dir, resolved_session_id, error_result = self._resolve_session_target(sessions_dir)
        if error_result is not None or target_dir is None or resolved_session_id is None:
            return error_result or DiffResult(
                status=DiffStatus.SESSION_NOT_FOUND,
                errors=["Session resolution failed."],
            )

        return self._read_patch_artifact(target_dir, resolved_session_id)

    def execute(self) -> DiffResult:
        """Collect diff artifact and render results to Rich output."""
        result = self.collect()
        render_diff(result, raw=self.raw, output=self.output, cwd=self.path)
        return result
