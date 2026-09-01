"""Step domain facade."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from worktree.core.step.assertions import evaluate_assertions
from worktree.core.step.models import (
    AssertionResult,
    ConditionEvaluationResult,
    ExecutionIdentity,
    ExecutionMetadata,
    PreviousStepMetadata,
    StepAssert,
    StepDefinition,
    StepExecutionContext,
    StepResult,
)
from worktree.core.step.runner import StepExecution
from worktree.core.step.services.conditions import (
    ParsedCondition,
    evaluate_condition,
    parse_condition_expression,
    validate_condition_expression,
)
from worktree.core.step.services.loader import load_step_by_id, load_step_definition
from worktree.core.step.services.metadata import (
    build_execution_metadata,
    metadata_to_env,
    previous_step_metadata_from_result,
)
from worktree.core.step.services.resolver import resolve_step_definition


class Step:
    """Unified entrypoint for step definition, resolution, and execution."""

    @staticmethod
    def load(source: dict[str, Any] | Path | str, *, path: Path | None = None) -> StepDefinition:
        """Load a StepDefinition from dictionary, file path, or catalog step ID."""
        if isinstance(source, dict):
            return StepDefinition(**source)
        if isinstance(source, Path):
            return load_step_definition(source)
        if isinstance(source, str):
            p = Path(source)
            if p.is_file():
                return load_step_definition(p)
            return load_step_by_id(source, path=path or Path("."))
        raise TypeError(f"Unsupported source type for Step.load: {type(source)}")

    @staticmethod
    def load_by_id(step_id: str, *, path: Path | None = None) -> StepDefinition:
        """Load a reusable step from catalog by ID or name."""
        return load_step_by_id(step_id, path=path or Path("."))

    @staticmethod
    def resolve(step: StepDefinition, *, path: Path | None = None) -> StepDefinition:
        """Resolve shorthand step fields (e.g. `uses: ...` or `run: ...`)."""
        return resolve_step_definition(step, path=path)

    @staticmethod
    def run(
        step: StepDefinition,
        sandbox_path: Path,
        *,
        context: dict[str, Any] | None = None,
        on_output: Callable[[str, str], None] | None = None,
        step_index: int = 1,
        initial_attempt: int = 1,
        iteration_index: int = 1,
        identity: ExecutionIdentity | None = None,
        previous_step: PreviousStepMetadata | None = None,
        steps: Sequence[PreviousStepMetadata] | None = None,
    ) -> StepResult:
        """Execute a step synchronously within a sandbox directory."""
        exec_context = StepExecutionContext(
            step=step,
            sandbox_path=sandbox_path,
            context=context,
            on_output=on_output,
            step_index=step_index,
            initial_attempt=initial_attempt,
            iteration_index=iteration_index,
            identity=identity,
            previous_step=previous_step,
            steps=steps,
        )
        return StepExecution(exec_context).run()

    @staticmethod
    def evaluate_assertions(
        assert_config: StepAssert,
        *,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
        sandbox_path: Path = Path("."),
    ) -> AssertionResult:
        """Evaluate a step's assert criteria."""
        return evaluate_assertions(
            assert_config,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            sandbox_path=sandbox_path,
        )

    @staticmethod
    def evaluate_condition(
        expression: str,
        *,
        iteration_index: int = 1,
        step_results: dict[str, StepResult] | None = None,
    ) -> ConditionEvaluationResult:
        """Parse and evaluate a single condition expression."""
        return evaluate_condition(
            expression,
            iteration_index=iteration_index,
            step_results=step_results,
        )

    @staticmethod
    def parse_condition(expression: str) -> ParsedCondition | None:
        """Parse condition string into structured ParsedCondition."""
        return parse_condition_expression(expression)

    @staticmethod
    def validate_condition(
        expression: str,
        known_step_ids: set[str] | None = None,
    ) -> list[str]:
        """Validate condition expression syntax and step references."""
        return validate_condition_expression(expression, known_step_ids=known_step_ids)

    @staticmethod
    def build_metadata(
        step: StepDefinition,
        *,
        step_index: int = 1,
        attempt: int = 1,
        iteration_index: int = 1,
        identity: ExecutionIdentity | None = None,
        previous_step: PreviousStepMetadata | None = None,
        steps: Sequence[PreviousStepMetadata] | None = None,
    ) -> ExecutionMetadata:
        """Build execution metadata container for step interpolation and environment."""
        return build_execution_metadata(
            step,
            step_index=step_index,
            attempt=attempt,
            iteration_index=iteration_index,
            identity=identity,
            previous_step=previous_step,
            steps=steps,
        )

    @staticmethod
    def metadata_to_env(metadata: ExecutionMetadata) -> dict[str, str]:
        """Convert step execution metadata to environment variables map."""
        return metadata_to_env(metadata)

    @staticmethod
    def previous_step_metadata(result: StepResult, *, step_index: int = 1) -> PreviousStepMetadata:
        """Construct PreviousStepMetadata from a completed StepResult."""
        return previous_step_metadata_from_result(result, step_index=step_index)
