from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.harness.assertions import assert_model_equal
from worktree.core.step.models import (
    StepAssert,
    StepDefinition,
    StepExecutionContext,
    StepResult,
    StepType,
)
from worktree.core.step.runner import StepExecution

pytestmark = pytest.mark.unit


@pytest.mark.unit
class StepRunnerAssertionContractTests:
    """Contract tests for step runner assertion evaluation and status resolution."""

    def test_assertion_failure_marks_step_failed_preserving_exit_code_zero(self, tmp_path: Path) -> None:
        """A step whose process exits 0 but whose assertion fails reports failed status with exit_code 0."""
        step = StepDefinition(
            id="test-assert-fail",
            type=StepType.COMMAND,
            command=f"{sys.executable} -c \"print('ok')\"",
            assert_=StepAssert(file_exists="missing.bin"),
        )
        result = StepExecution(StepExecutionContext(step=step, sandbox_path=tmp_path)).run()

        assert_model_equal(
            result,
            StepResult(
                step_id="test-assert-fail",
                status="failed",
                exit_code=0,
                stdout="ok\n",
                stderr="",
                duration_seconds=0.0,
                attempts=1,
                error_message=(
                    "Step 'test-assert-fail' failed assertion checks:\n"
                    "  [FAIL] file_exists: path 'missing.bin' does not exist"
                ),
            ),
            exclude={"duration_seconds"},
        )
        assert result.duration_seconds >= 0.0
