"""Class-based execution service for blueprint resume commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from worktree.core.blueprint import (
    BlueprintKind,
    BlueprintRunResult,
)
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogRepository, RunRecord, RunsRepository
from worktree.core.engine.engine import Engine
from worktree.core.engine.exceptions import EngineResumeError, EngineRuntimeError
from worktree.core.runtime import (
    FailurePrompter,
    RunObserver,
    RunOutcome,
)


@dataclass
class BlueprintResumeService:
    """Service encapsulating the paused session resume lifecycle."""

    path: Path
    db: RunsRepository
    catalog_db: CatalogRepository
    session_id: str | None = None
    non_interactive: bool = False
    observer: RunObserver | None = None
    failure_prompter: FailurePrompter | None = None
    warnings: list[str] = field(default_factory=list)

    def execute(self) -> BlueprintRunResult:
        """Find session if omitted, classify and resume via Engine."""
        target_session_id, _, resolve_error = self._resolve_target_session()
        if resolve_error is not None or not target_session_id:
            return self._fail(resolve_error or "No paused session found to resume.")

        catalog = Catalog(path=self.path, db=self.catalog_db)

        try:
            run_outcome = Engine(self.path, db=self.db, catalog=catalog).resume(
                target_session_id,
                observer=self.observer,
                failure_prompter=self.failure_prompter,
                non_interactive=self.non_interactive,
            )
        except (EngineResumeError, EngineRuntimeError) as exc:
            return self._fail(str(exc))

        return self._finalize(target_session_id, run_outcome)

    def _resolve_target_session(self) -> tuple[str, BlueprintKind | None, str | None]:
        if not self.session_id:
            record = self.db.get_latest_paused()
            if record is None:
                return "", None, "No paused session found to resume."
            return record.session_id, record.kind, None

        record = self._load_record(self.session_id)
        target_kind = record.kind if record is not None else None
        return self.session_id, target_kind, None

    def _fail(self, message: str) -> BlueprintRunResult:
        return BlueprintRunResult(
            run_record=None,
            errors=[message],
            warnings=self.warnings,
        )

    def _load_record(self, session_id: str) -> RunRecord | None:
        try:
            return self.db.get(session_id)
        except Exception as exc:
            self.warnings.append(f"Failed to load run record for '{session_id}': {exc}")
            return None

    def _finalize(self, session_id: str, run_outcome: RunOutcome) -> BlueprintRunResult:
        self.warnings.extend(run_outcome.warnings)
        record = self._load_record(session_id)
        return BlueprintRunResult(
            run_record=record,
            errors=list(run_outcome.errors),
            warnings=self.warnings,
        )
