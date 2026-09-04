"""Class-based execution service for blueprint run commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from worktree.core.blueprint import (
    Blueprint,
    BlueprintKind,
    BlueprintLoadError,
    BlueprintNotFoundError,
    BlueprintRunResult,
    BlueprintValidationError,
)
from worktree.core.catalog import Catalog
from worktree.core.db import CatalogRepository, RunRecord, RunsRepository, RunStatus
from worktree.core.engine.engine import Engine
from worktree.core.engine.exceptions import EngineInputError, EngineRuntimeError
from worktree.core.engine.models import RunRequest
from worktree.core.engine.services.reconcile import reconcile_stale_runs
from worktree.core.inputs.services.resolve import format_input_error_message
from worktree.core.runtime import (
    FailurePrompter,
    RunObserver,
    RunOutcome,
)


@dataclass
class BlueprintRunService:
    """Service encapsulating the blueprint execution lifecycle."""

    name: str
    path: Path
    runs_db: RunsRepository
    catalog_db: CatalogRepository
    kind: BlueprintKind | None = None
    no_sandbox: bool = False
    keep: bool = False
    agent: str | None = None
    session_id: str | None = None
    cli_args: list[str] | None = None
    non_interactive: bool = False
    auto_apply: bool = False
    observer: RunObserver | None = None
    failure_prompter: FailurePrompter | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def _kind_label(self) -> str:
        return self.kind.value if self.kind is not None else "blueprint"

    def execute(self) -> BlueprintRunResult:
        """Run the full execution pipeline and return the outcome."""
        reconciliation_result = reconcile_stale_runs(self.runs_db, path=self.path)
        if reconciliation_result.warning:
            self.warnings.append(reconciliation_result.warning)

        catalog = Catalog(path=self.path, db=self.catalog_db)
        blueprint, fail_outcome = self._load_blueprint(catalog)
        if fail_outcome is not None or blueprint is None:
            return fail_outcome or self._fail(f"Failed to load {self._kind_label} '{self.name}'.")

        if self.kind is None:
            self.kind = blueprint.kind

        try:
            run_outcome = Engine(self.path, db=self.runs_db, catalog=catalog).run(
                blueprint,
                RunRequest(
                    cli_args=self.cli_args,
                    use_sandbox=not self.no_sandbox,
                    keep=self.keep,
                    agent=self.agent,
                    session_id=self.session_id,
                    observer=self.observer,
                    failure_prompter=self.failure_prompter,
                    non_interactive=self.non_interactive,
                    auto_apply=self.auto_apply,
                ),
            )
        except EngineInputError as exc:
            return self._fail(
                format_input_error_message(
                    kind=self._kind_label,
                    name=self.name,
                    result=exc.result,
                    declarations=blueprint.inputs,
                )
            )
        except EngineRuntimeError as exc:
            return self._fail(str(exc))

        return self._finalize(run_outcome)

    def _fail(self, message: str) -> BlueprintRunResult:
        return BlueprintRunResult(
            run_record=None,
            errors=[message],
            warnings=self.warnings,
        )

    def _load_blueprint(self, catalog: Catalog) -> tuple[Blueprint | None, BlueprintRunResult | None]:
        kind_str = self.kind.value if self.kind else "blueprint"
        try:
            blueprint = Blueprint.load(self.name, catalog=catalog)
        except (BlueprintNotFoundError, BlueprintLoadError) as exc:
            msg = str(exc) if str(exc) else f"Failed to resolve {kind_str}."
            return None, self._fail(msg)
        except BlueprintValidationError as exc:
            msg = str(exc) if str(exc) else f"{kind_str.capitalize()} definition is invalid."
            return None, self._fail(msg)

        if self.kind is not None and blueprint.kind is not self.kind:
            msg = (
                f"Blueprint '{self.name}' is a {blueprint.kind.value}; "
                f"wt {self.kind.value} run requires a {self.kind.value}."
            )
            return None, self._fail(msg)

        return blueprint, None

    def _load_record(self, session_id: str) -> RunRecord | None:
        try:
            return self.runs_db.get(session_id)
        except Exception as exc:
            self.warnings.append(f"Failed to load run record for '{session_id}': {exc}")
            return None

    def _fallback_record(
        self,
        session_id: str,
        status: RunStatus,
        error: str | None,
    ) -> RunRecord:
        return RunRecord(
            id=-1,
            session_id=session_id,
            blueprint_name=self.name,
            kind=self.kind or BlueprintKind.TASK,
            branch_name="",
            status=status,
            started_at="",
            completed_at=None,
            error_message=error,
        )

    def _finalize(self, run_outcome: RunOutcome) -> BlueprintRunResult:
        sid = run_outcome.session_id or ""
        self.warnings.extend(run_outcome.warnings)
        record = self._load_record(sid) if sid else None
        primary_error = run_outcome.errors[0] if run_outcome.errors else None
        final_record = record or self._fallback_record(
            sid,
            run_outcome.status,
            primary_error,
        )

        return BlueprintRunResult(
            run_record=final_record,
            errors=list(run_outcome.errors),
            warnings=self.warnings,
        )
