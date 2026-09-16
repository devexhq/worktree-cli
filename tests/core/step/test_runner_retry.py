from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.harness.builders import StepBuilder
from tests.harness.matchers import ANY_DURATION, assert_model_equal
from worktree.core.step.models import StepExecutionContext, StepResult
from worktree.core.step.runner import StepExecution

pytestmark = pytest.mark.integration


@pytest.mark.integration
class StepRetryExecutionTests:
    """Integration tests verifying step execution retry loops and environment propagation."""

    def test_step_command_adapts_behavior_based_on_attempt_counter(self, tmp_path: Path) -> None:
        """Verify step command receives incremented WT_STEP_ATTEMPT and succeeds on retry."""
        script_file = tmp_path / "retry_script.py"
        script_file.write_text(
            "import os\n"
            "import sys\n\n"
            "attempt = os.environ.get('WT_STEP_ATTEMPT', '0')\n"
            "if attempt == '1':\n"
            "    print('attempt 1')\n"
            "    sys.exit(1)\n"
            "elif attempt == '2':\n"
            "    print('attempt 2 succeeded')\n"
            "    sys.exit(0)\n"
            "else:\n"
            "    sys.exit(2)\n"
        )
        cmd = f"{sys.executable} retry_script.py"
        step = StepBuilder.command(cmd).with_id("retry-adapt").with_retry(max_retries=2, backoff_ms=0).build()
        result = StepExecution(StepExecutionContext(step=step, sandbox_path=tmp_path)).run()

        assert_model_equal(
            result,
            StepResult.model_construct(
                step_id="retry-adapt",
                status="completed",
                exit_code=0,
                stdout="attempt 2 succeeded\n",
                stderr="",
                duration_seconds=ANY_DURATION,
                attempts=2,
                error_message=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
        assert result.duration_seconds >= 0.0


@pytest.mark.integration
class StepRunnerRobustnessTests:
    """Integration tests verifying runner resilience against stream observer callback exceptions."""

    def test_observer_callback_exception_does_not_halt_step_execution(self, tmp_path: Path) -> None:
        """Verify observer callback exceptions do not prematurely abort subprocess execution."""
        cmd = (
            f"{sys.executable} -c "
            '"import sys, pathlib; '
            "print('line 1', flush=True); "
            "print('line 2', flush=True); "
            "pathlib.Path('finished.marker').write_text('done'); "
            'sys.exit(0)"'
        )

        def failing_observer(stream: str, line: str) -> None:
            if line.startswith("line 1"):
                raise RuntimeError("observer crashed")

        step = StepBuilder.command(cmd).with_id("robustness-observer").build()
        result = StepExecution(
            StepExecutionContext(
                step=step,
                sandbox_path=tmp_path,
                on_output=failing_observer,
            )
        ).run()

        marker_file = tmp_path / "finished.marker"
        assert marker_file.exists()
        assert marker_file.read_text().strip() == "done"

        assert_model_equal(
            result,
            StepResult.model_construct(
                step_id="robustness-observer",
                status="failed",
                exit_code=1,
                stdout="line 1\nline 2\n",
                stderr="",
                duration_seconds=ANY_DURATION,
                attempts=1,
                error_message="Command pipe error: Output callback error on stdout: observer crashed",
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
        assert result.duration_seconds >= 0.0
