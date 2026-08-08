"""Top-level workflow iteration orchestration: ``WorkflowRunner`` and ``run_workflow_iteration``.

Resolves config/sandbox/agent setup, then runs the per-attempt dispatch workflow
against a shared ``_WorkflowContext`` (see ``steps.py``), delegating each stage
to a ``_run_*_step`` function and handling sandbox cleanup.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from getworktree.common.fs import get_session_dir
from getworktree.core.config.loader import load_config_result
from getworktree.core.config.models import WorktreeConfig
from getworktree.core.db import (
    RunStatus,
    WorkflowsDb,
)
from getworktree.core.git_sandbox import (
    GitSandboxManager,
    SandboxSession,
    should_cleanup_sandbox,
)
from getworktree.core.workflows.models import WorkflowDefinition
from getworktree.core.workflows.runner.helpers import (
    _emit,
    _now_iso,
    capture_and_persist_diff,
    resolve_max_attempts,
)
from getworktree.core.workflows.runner.steps import (
    _run_agent_step,
    _run_approval_step,
    _run_patch_step,
    _run_trigger_step,
    _WorkflowContext,
)
from getworktree.core.workflows.runner_models import (
    AttemptRecord,
    StepOutcome,
    StopReason,
    WorkflowFinalStatus,
    WorkflowRunOptions,
    WorkflowRunResult,
)
from getworktree.core.workflows.safety import SafetyState

if TYPE_CHECKING:
    from getworktree.core.workflows.agents.base import AgentAdapter


class WorkflowRunner:
    """Class-based orchestrator for executing workflow iteration sessions."""

    def __init__(
        self,
        workflow: WorkflowDefinition,
        *,
        cwd: Path | None = None,
        options: WorkflowRunOptions | None = None,
    ) -> None:
        self.workflow = workflow
        self.root = (cwd or Path.cwd()).expanduser().resolve()
        self.options = options or WorkflowRunOptions()

        self.workflow_name = workflow.name
        self.config: WorktreeConfig | None = self.options.config
        self.agent: AgentAdapter | None = self.options.agent
        self.max_attempts: int = 0

        self.manager: GitSandboxManager | None = None
        self.session: SandboxSession | None = None
        self.sid: str = self.options.session_id or ""
        self.sandbox_path: Path = self.root

        self.attempts: list[AttemptRecord] = []
        self.run_errors: list[str] = []
        self.warnings: list[str] = []
        self.final_status: WorkflowFinalStatus = WorkflowFinalStatus.FAILED
        self.stop_reason: StopReason | str = StopReason.MAX_ATTEMPTS_EXHAUSTED
        self.command_passed: bool | None = None

    def _resolve_workflow_requirement[T](self, setting: str, default_value: T, *, config_section: str = "sandbox") -> T:
        """Resolve workflow requirement from options, config section or a default value."""
        options_value = getattr(self.options, setting, None)
        if options_value is not None and options_value is not None:
            return options_value  # type: ignore[return-value]

        workflow_value = getattr(self.workflow, f"_{setting}", None)
        if workflow_value is not None and workflow_value is not None:
            return workflow_value  # type: ignore[return-value]

        section = getattr(self.config, config_section, None)
        if section is not None:
            section_value = getattr(section, setting, None)
            if section_value is not None:
                return section_value  # type: ignore[return-value]

        return default_value

    def setup(self) -> WorkflowRunResult | None:
        """Resolve configuration, attempt limits, database run, and create sandbox."""
        if self.config is None:
            load = load_config_result(cwd=self.root)
            if not load.ok or load.config is None:
                detail = load.errors[0] if load.errors else str(load.status)
                return WorkflowRunResult(
                    status=WorkflowFinalStatus.FAILED,
                    session_id=self.sid,
                    workflow_name=self.workflow_name,
                    stop_reason=StopReason.CONFIGURATION_ERROR,
                    errors=[f"Workflow run configuration error: {detail}"],
                )
            self.config = load.config

        try:
            self.max_attempts = resolve_max_attempts(
                workflow=self.workflow,
                config=self.config,
                caller_max_attempts=self.options.max_attempts,
            )
        except Exception as exc:  # defensive
            return WorkflowRunResult(
                status=WorkflowFinalStatus.FAILED,
                session_id=self.sid,
                workflow_name=self.workflow_name,
                stop_reason=StopReason.CONFIGURATION_ERROR,
                errors=[f"Workflow run configuration error: {exc}"],
            )

        if self.max_attempts < 1:
            return WorkflowRunResult(
                status=WorkflowFinalStatus.FAILED,
                session_id=self.sid,
                workflow_name=self.workflow_name,
                stop_reason=StopReason.CONFIGURATION_ERROR,
                max_attempts=self.max_attempts,
                errors=[
                    f"Workflow run configuration error: effective max_attempts is {self.max_attempts} (must be >= 1)"
                ],
            )

        self.resolved_auto = bool(self._resolve_workflow_requirement("auto_clean", True))
        self.resolved_keep = bool(self._resolve_workflow_requirement("keep_on_failure", True))
        self.resolved_require = bool(
            self._resolve_workflow_requirement("require_before_apply", True, config_section="approval")
        )
        self.stop_when = self._resolve_workflow_requirement("stop_when", {"trigger_passes", "unfixable", "user_abort"})

        if not self.options.no_sandbox:
            self.manager = GitSandboxManager(cwd=self.root)
            create_result = self.manager.create_sandbox_result(
                session_id=self.options.session_id,
                include_wip=self.options.include_wip,
            )

            if not create_result.ok or create_result.session is None:
                errors = list(create_result.errors) or [f"Sandbox create failed: {create_result.status}"]
                return WorkflowRunResult(
                    status=WorkflowFinalStatus.FAILED,
                    session_id=self.options.session_id or "",
                    workflow_name=self.workflow_name,
                    stop_reason=StopReason.SANDBOX_CREATE_FAILED,
                    max_attempts=self.max_attempts,
                    errors=errors,
                )

            self.session = create_result.session
            self.sandbox_path = self.session.sandbox_path
            self.sid = self.session.session_id
        else:
            self.sid = self.options.session_id or f"wf_{uuid.uuid4().hex[:8]}"
            self.sandbox_path = self.root
            self.session = SandboxSession(
                session_id=self.sid,
                name=None,
                target_branch=f"worktree/{self.sid}",
                base_commit="HEAD",
                sandbox_path=self.root,
                created_at="",
            )

        try:
            WorkflowsDb(self.root).insert(
                session_id=self.sid,
                workflow_name=self.workflow_name,
                branch_name=self.session.target_branch,
                status=RunStatus.RUNNING,
            )
        except Exception as exc:
            self.warnings.append(f"Failed to record workflow run start in database: {exc}")

        session_dir = get_session_dir(self.root, self.sid)
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.warnings.append(f"Failed to create session directory '{session_dir}': {exc}")

        _emit(
            self.options.on_event,
            "session_start",
            session_id=self.sid,
            sandbox_path=str(self.sandbox_path),
            workflow_name=self.workflow_name,
            max_attempts=self.max_attempts,
            wip=self.session.wip_applied,
            wip_paths=list(self.session.wip_paths),
        )

        if self.agent is None:
            from getworktree.core.workflows.agents.factory import get_agent_adapter

            try:
                self.agent = get_agent_adapter("local", config=self.config.agent)
            except ValueError as exc:
                self.run_errors.append(str(exc))
                self.final_status = WorkflowFinalStatus.FAILED
                self.stop_reason = StopReason.CONFIGURATION_ERROR
                return self.finalize()

        return None

    def execute_attempts(self) -> None:
        """Execute the per-attempt loop across _run_*_step functions."""
        assert self.config is not None
        assert self.agent is not None

        reject_binary = (
            getattr(self.workflow, "_reject_binary", None)
            if getattr(self.workflow, "_reject_binary", None) is not None
            else self.config.patch.reject_binary_changes
        )
        max_files = getattr(self.workflow, "_max_files", None) or 30
        max_patch_kb = getattr(self.workflow, "_max_patch_kb", None) or 1024
        resolved_session_timeout = (
            self.options.session_timeout_seconds
            if self.options.session_timeout_seconds is not None
            else self.config.sandbox.default_timeout_seconds
        )
        resolved_detect_repeat = self.config.workflow.detect_repeat_failures
        safety = SafetyState()

        ctx = _WorkflowContext(
            workflow=self.workflow,
            config=self.config,
            agent=self.agent,
            sandbox_path=self.sandbox_path,
            session_id=self.sid,
            max_attempts=self.max_attempts,
            stop_when=self.stop_when,
            resolved_require=self.resolved_require,
            reject_binary=reject_binary,
            max_files=max_files,
            max_patch_kb=max_patch_kb,
            resolved_detect_repeat=resolved_detect_repeat,
            resolved_session_timeout=resolved_session_timeout,
            approve_patch=self.options.approve_patch,
            abort_event=self.options.abort_event,
            on_event=self.options.on_event,
            on_attempt_end=self.options.on_attempt_end,
            prompt_dump_dir=self.options.prompt_dump_dir,
            attempts=self.attempts,
            run_errors=self.run_errors,
            safety=safety,
        )

        def _apply(outcome: StepOutcome) -> bool:
            if outcome.continue_workflow:
                return True
            if outcome.final_status is not None:
                self.final_status = outcome.final_status
            if outcome.stop_reason is not None:
                self.stop_reason = outcome.stop_reason
            self.command_passed = outcome.command_passed
            return False

        for attempt_idx in range(1, self.max_attempts + 1):
            if ctx.aborted():
                self.final_status = WorkflowFinalStatus.ABORTED
                self.stop_reason = StopReason.USER_ABORT
                break

            if ctx.timed_out():
                self.final_status = WorkflowFinalStatus.FAILED
                self.stop_reason = StopReason.SESSION_TIMEOUT
                self.command_passed = False
                break

            record = AttemptRecord(attempt=attempt_idx, started_at=_now_iso())
            _emit(
                self.options.on_event,
                "attempt_start",
                attempt=attempt_idx,
                max_attempts=self.max_attempts,
            )

            trigger_outcome, trigger_result = _run_trigger_step(ctx, attempt_idx, record)
            if trigger_outcome is not None:
                if _apply(trigger_outcome):
                    continue
                break
            assert trigger_result is not None

            agent_outcome, agent_response = _run_agent_step(ctx, attempt_idx, record, trigger_result=trigger_result)
            if agent_outcome is not None:
                if _apply(agent_outcome):
                    continue
                break
            assert agent_response is not None

            approval_outcome = _run_approval_step(ctx, attempt_idx, record, agent_response)
            if approval_outcome is not None:
                if _apply(approval_outcome):
                    continue
                break

            patch_outcome = _run_patch_step(ctx, attempt_idx, record, agent_response)
            if _apply(patch_outcome):
                continue
            break
        else:
            if self.final_status != WorkflowFinalStatus.PASSED:
                self.final_status = WorkflowFinalStatus.FAILED
                self.stop_reason = StopReason.MAX_ATTEMPTS_EXHAUSTED
                self.command_passed = False

    def finalize(self) -> WorkflowRunResult:
        """Record final DB status, capture git diff, perform sandbox cleanup, and build result."""
        if self.command_passed is None and self.final_status == WorkflowFinalStatus.PASSED:
            self.command_passed = True
        elif self.command_passed is None and self.final_status in {
            WorkflowFinalStatus.FAILED,
            WorkflowFinalStatus.UNFIXABLE,
        }:
            self.command_passed = False

        if self.session is not None:
            self.session.command_passed = self.command_passed
            capture_and_persist_diff(session=self.session, cwd=self.root, warnings=self.warnings)

        run_status = (
            RunStatus.COMPLETED
            if self.final_status == WorkflowFinalStatus.PASSED
            else RunStatus.CANCELLED
            if self.final_status == WorkflowFinalStatus.ABORTED
            else RunStatus.FAILED
        )
        stop_reason_str = self.stop_reason.value if hasattr(self.stop_reason, "value") else str(self.stop_reason)
        err_msg = (
            "; ".join(self.run_errors)
            if self.run_errors
            else (f"Stop reason: {stop_reason_str}" if run_status != RunStatus.COMPLETED else None)
        )

        try:
            WorkflowsDb(self.root).update_status(
                session_id=self.sid,
                status=run_status,
                error_message=err_msg,
            )
        except Exception as exc:
            self.warnings.append(f"Failed to update workflow run status in database: {exc}")

        will_clean = should_cleanup_sandbox(
            auto_clean=self.resolved_auto,
            keep_on_failure=self.resolved_keep,
            command_passed=self.command_passed,
        )

        if will_clean:
            if self.session is not None and self.manager is not None:
                self.manager.cleanup_sandbox(self.session)
            retained = False
            result_sandbox: Path | None = None
        else:
            retained = True
            result_sandbox = self.sandbox_path

        return WorkflowRunResult(
            status=self.final_status,
            session_id=self.sid,
            workflow_name=self.workflow_name,
            sandbox_path=result_sandbox,
            attempts=self.attempts,
            stop_reason=stop_reason_str,
            errors=self.run_errors,
            warnings=self.warnings,
            max_attempts=self.max_attempts,
            sandbox_retained=retained,
        )

    def run(self) -> WorkflowRunResult:
        """Run full setup -> execute_attempts -> finalize pipeline."""
        early_result = self.setup()
        if early_result is not None:
            return early_result
        self.execute_attempts()
        return self.finalize()


def run_workflow_iteration(
    workflow: WorkflowDefinition,
    *,
    cwd: Path | None = None,
    options: WorkflowRunOptions | None = None,
) -> WorkflowRunResult:
    """Run one full workflow session attempt cycle.

    Args:
        workflow: Validated workflow definition.
        cwd: Repository root. Defaults to process CWD.
        options: Optional workflow run options and callbacks.

    Returns:
        Structured :class:`WorkflowRunResult` (never raises for classified paths).
    """
    runner = WorkflowRunner(workflow=workflow, cwd=cwd, options=options)
    return runner.run()
