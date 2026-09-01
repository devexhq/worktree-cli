"""Tests for BlueprintRenderer plain-text failure bodies."""

from __future__ import annotations

from pathlib import Path

from worktree.core.blueprint import BlueprintKind
from worktree.core.blueprint.renderers import (
    BlueprintRenderer,
    RenderableRunOutcome,
    Renderer,
)
from worktree.core.db import RunStatus
from worktree.core.runtime import RunOutcome
from worktree.core.step import StepResult


def _failed_outcome(**overrides: object) -> RunOutcome:
    payload: dict[str, object] = {
        "status": RunStatus.FAILED,
        "sandbox_path": Path("/tmp/run"),
    }
    payload.update(overrides)
    return RunOutcome.model_validate(payload)


def _step_result(step_id: str, error_message: str | None) -> StepResult:
    return StepResult(
        step_id=step_id,
        status="failed",
        exit_code=1,
        stdout="",
        stderr="",
        duration_seconds=0.1,
        error_message=error_message,
    )


class DuckOutcome:
    def __init__(self, errors: list[str] | None = None, step_results: list[StepResult] | None = None) -> None:
        self.errors = errors or []
        self.step_results = step_results or []


class BlueprintRendererProtocolTests:
    def test_instance_satisfies_renderer_protocol(self) -> None:
        renderer = BlueprintRenderer(BlueprintKind.TASK)

        assert isinstance(renderer, Renderer)

    def test_duck_typed_outcome_satisfies_renderable_run_outcome(self) -> None:
        duck = DuckOutcome(errors=["duck boom"])
        assert isinstance(duck, RenderableRunOutcome)
        rendered = BlueprintRenderer(BlueprintKind.TASK).render(duck)
        assert rendered == "duck boom"


class BlueprintRendererRenderTests:
    def test_top_level_errors_win(self) -> None:
        outcome = _failed_outcome(errors=["top-level boom"])

        assert BlueprintRenderer(BlueprintKind.TASK).render(outcome) == "top-level boom"
        assert BlueprintRenderer(BlueprintKind.WORKFLOW).render(outcome) == "top-level boom"

    def test_joins_step_errors(self) -> None:
        outcome = _failed_outcome(
            step_results=[
                _step_result("s1", "step one failed"),
                _step_result("s2", "step two failed"),
            ]
        )

        assert BlueprintRenderer(BlueprintKind.TASK).render(outcome) == "step one failed\nstep two failed"

    def test_skips_empty_step_errors(self) -> None:
        outcome = _failed_outcome(
            step_results=[
                _step_result("s1", None),
                _step_result("s2", "kept"),
            ]
        )

        assert BlueprintRenderer(BlueprintKind.TASK).render(outcome) == "kept"

    def test_includes_stderr_detail_when_available(self) -> None:
        outcome = _failed_outcome(
            errors=["Step 'run-tests' failed: Command failed with exit code 127."],
            step_results=[
                StepResult(
                    step_id="run-tests",
                    status="failed",
                    exit_code=127,
                    stdout="",
                    stderr="sh: 1: pytest: not found",
                    duration_seconds=0.1,
                    error_message="Command failed with exit code 127.",
                )
            ],
        )

        rendered = BlueprintRenderer(BlueprintKind.TASK).render(outcome)
        assert "Step 'run-tests' failed: Command failed with exit code 127." in rendered
        assert "sh: 1: pytest: not found" in rendered

    def test_kind_specific_execution_fallback(self) -> None:
        outcome = _failed_outcome()

        assert BlueprintRenderer(BlueprintKind.TASK).render(outcome) == "Task execution failed."
        assert BlueprintRenderer(BlueprintKind.WORKFLOW).render(outcome) == "Workflow execution failed."


class BlueprintRendererResolveTests:
    def test_joins_errors(self) -> None:
        assert BlueprintRenderer(BlueprintKind.TASK).render_resolve_failure(["err-a", "err-b"]) == "err-a\n\nerr-b"

    def test_kind_specific_fallback(self) -> None:
        assert BlueprintRenderer(BlueprintKind.TASK).render_resolve_failure([]) == "Failed to resolve task."
        assert BlueprintRenderer(BlueprintKind.WORKFLOW).render_resolve_failure([]) == "Failed to resolve workflow."


class BlueprintRendererValidateTests:
    def test_joins_errors(self) -> None:
        assert BlueprintRenderer(BlueprintKind.WORKFLOW).render_validate_failure(["schema bad", "more"]) == (
            "schema bad\n\nmore"
        )

    def test_kind_specific_fallback(self) -> None:
        assert BlueprintRenderer(BlueprintKind.TASK).render_validate_failure([]) == "Task definition is invalid."
        assert (
            BlueprintRenderer(BlueprintKind.WORKFLOW).render_validate_failure([]) == "Workflow definition is invalid."
        )
