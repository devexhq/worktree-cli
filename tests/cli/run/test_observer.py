"""Unit tests for runtime execution observers and UiDispatcher integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tests.helpers import make_dispatcher_with_buffer
from worktree.cli.run.observer import DispatcherRunObserver, resolve_cli_observer
from worktree.cli.ui.dispatcher import UiDispatcher
from worktree.cli.ui.events import (
    LoopLifecycleEvent,
    SandboxLifecycleEvent,
    StepDoneEvent,
    StepOutputEvent,
    StepStartEvent,
)
from worktree.core.step import ConditionEvaluationResult, StepDefinition, StepResult


class DispatcherRunObserverTests:
    """Tests for DispatcherRunObserver event dispatching and lifecycle."""

    def test_context_manager_live_lifecycle(self) -> None:
        dispatcher = MagicMock(spec=UiDispatcher)
        observer = DispatcherRunObserver(dispatcher, live=True)

        with observer:
            dispatcher.start_live.assert_called_once()
            assert dispatcher.stop_live.call_count == 0

        dispatcher.stop_live.assert_called_once()

    def test_context_manager_non_live_lifecycle(self) -> None:
        dispatcher = MagicMock(spec=UiDispatcher)
        observer = DispatcherRunObserver(dispatcher, live=False)

        with observer:
            assert dispatcher.start_live.call_count == 0
            assert dispatcher.stop_live.call_count == 0

        assert dispatcher.start_live.call_count == 0
        assert dispatcher.stop_live.call_count == 0

    def test_callbacks_dispatch_typed_events(self) -> None:
        dispatcher = MagicMock(spec=UiDispatcher)
        observer = DispatcherRunObserver(dispatcher)

        # Sandbox ready
        observer.on_sandbox_ready(Path("/tmp/sbx"), active=True)
        dispatcher.dispatch.assert_called_with(SandboxLifecycleEvent(action="ready", path="/tmp/sbx", active=True))

        # Step start
        step = StepDefinition(id="s1", name="lint", run="ruff check")
        observer.on_step_start(1, 2, step)
        dispatcher.dispatch.assert_called_with(
            StepStartEvent(idx=1, total=2, step_id="s1", name="lint", command="ruff check")
        )

        # Step output
        observer.on_step_output(1, 2, step, "output line 1\n", stream="stdout")
        dispatcher.dispatch.assert_called_with(StepOutputEvent(step_id="s1", line="output line 1\n", stream="stdout"))

        # Step done
        result = StepResult(
            step_id="s1",
            status="completed",
            exit_code=0,
            stdout="output line 1",
            stderr="",
            duration_seconds=0.5,
        )
        observer.on_step_done(1, 2, result)
        dispatcher.dispatch.assert_called_with(
            StepDoneEvent(
                idx=1,
                total=2,
                step_id="s1",
                ok=True,
                exit_code=0,
                duration_seconds=0.5,
                error_message=None,
            )
        )

        # Loop lifecycle
        observer.on_loop_start("loop-1", 3)
        dispatcher.dispatch.assert_called_with(LoopLifecycleEvent(loop_id="loop-1", action="start", max_iterations=3))

        observer.on_loop_turn_start("loop-1", 1, 3)
        dispatcher.dispatch.assert_called_with(
            LoopLifecycleEvent(loop_id="loop-1", action="turn_start", turn=1, max_iterations=3)
        )

        cond_result = ConditionEvaluationResult(expression="exit_code == 0", passed=True, detail="ok")
        observer.on_loop_conditions_evaluated("loop-1", [cond_result], all_passed=True)
        dispatcher.dispatch.assert_called_with(
            LoopLifecycleEvent(
                loop_id="loop-1",
                action="conditions_evaluated",
                message="\\[loop-1] Evaluated 'until' conditions:\n  - exit_code == 0: ok",
            )
        )

        observer.on_loop_done("loop-1", "completed", 1)
        dispatcher.dispatch.assert_called_with(
            LoopLifecycleEvent(loop_id="loop-1", action="done", turn=1, status="completed")
        )

        # Sandbox cleanup
        observer.on_sandbox_cleanup(kept=True, path=Path("/tmp/sbx"))
        dispatcher.dispatch.assert_called_with(SandboxLifecycleEvent(action="cleanup", path="/tmp/sbx", kept=True))

    def test_callbacks_emit_terminal_output(self) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer()
        observer = DispatcherRunObserver(dispatcher)

        with observer:
            observer.on_sandbox_ready(Path("/tmp/sbx"), active=True)
            observer.on_step_start(1, 2, StepDefinition(id="step-1", run="echo 1", name="First Step"))
            observer.on_step_output(1, 2, StepDefinition(id="step-1", run="echo 1"), "output line 1")
            observer.on_step_done(
                1,
                2,
                StepResult(
                    step_id="step-1",
                    status="completed",
                    exit_code=0,
                    stdout="output line 1",
                    stderr="",
                    duration_seconds=0.1,
                ),
            )
            observer.on_loop_start("loop-test", 4)
            observer.on_loop_turn_start("loop-test", 1, 4)
            observer.on_loop_conditions_evaluated(
                "loop-test",
                [ConditionEvaluationResult(expression="exit_code == 0", passed=True, detail="exit_code is 0")],
                all_passed=True,
            )
            observer.on_loop_done("loop-test", "completed", 1)
            observer.on_sandbox_cleanup(kept=False, path=Path("/tmp/sbx"))

        output = buffer.getvalue()
        assert "Sandbox: Active (/tmp/sbx)" in output
        assert "[STEP 1/2] Executing First Step (command: echo 1)..." in output
        assert "output line 1" in output
        assert "[STEP 1/2] step-1 COMPLETED" in output
        assert "[loop-test] Starting loop block (max_iterations: 4)" in output
        assert "[loop-test] --- Iteration Turn 1/4 ---" in output
        assert "Evaluated 'until' conditions:" in output
        assert "[loop-test] Loop completed successfully in 1 iteration(s)." in output
        assert "Sandbox: Cleaned" in output


class ResolveCliObserverTests:
    """Tests for resolve_cli_observer factory."""

    def test_terminal_tty_enables_live(self) -> None:
        dispatcher, _ = make_dispatcher_with_buffer(force_terminal=True)
        observer = resolve_cli_observer(dispatcher, non_interactive=False, output_format="terminal")
        assert isinstance(observer, DispatcherRunObserver)
        assert observer._live is True

    def test_non_interactive_disables_live(self) -> None:
        dispatcher, _ = make_dispatcher_with_buffer(force_terminal=True)
        observer = resolve_cli_observer(dispatcher, non_interactive=True, output_format="terminal")
        assert isinstance(observer, DispatcherRunObserver)
        assert observer._live is False

    def test_json_format_disables_live(self) -> None:
        dispatcher, _ = make_dispatcher_with_buffer(force_terminal=True)
        observer = resolve_cli_observer(dispatcher, non_interactive=False, output_format="json")
        assert isinstance(observer, DispatcherRunObserver)
        assert observer._live is False

    def test_non_terminal_console_disables_live(self) -> None:
        dispatcher, _ = make_dispatcher_with_buffer(force_terminal=False)
        observer = resolve_cli_observer(dispatcher, non_interactive=False, output_format="terminal")
        assert isinstance(observer, DispatcherRunObserver)
        assert observer._live is False

    def test_live_mode_emits_terminal_output(self) -> None:
        """Verify resolve_cli_observer with live=True emits step, sandbox, and loop lifecycle output."""
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        observer = resolve_cli_observer(dispatcher, output_format="terminal")
        assert observer._live is True

        with observer:
            observer.on_sandbox_ready(Path("/tmp/sbx_live"), active=True)
            observer.on_step_start(1, 2, StepDefinition(id="step-1", run="echo live", name="Live Step"))
            observer.on_step_output(1, 2, StepDefinition(id="step-1", run="echo live"), "streaming output")
            observer.on_step_done(
                1,
                2,
                StepResult(
                    step_id="step-1",
                    status="completed",
                    exit_code=0,
                    stdout="streaming output",
                    stderr="",
                    duration_seconds=0.2,
                ),
            )
            observer.on_loop_start("loop-live", 3)
            observer.on_loop_turn_start("loop-live", 1, 3)
            observer.on_loop_conditions_evaluated(
                "loop-live",
                [ConditionEvaluationResult(expression="exit_code == 0", passed=False, detail="exit_code is 1")],
                all_passed=False,
                next_turn=2,
            )
            observer.on_loop_turn_start("loop-live", 2, 3)
            observer.on_loop_conditions_evaluated(
                "loop-live",
                [ConditionEvaluationResult(expression="exit_code == 0", passed=True, detail="exit_code is 0")],
                all_passed=True,
            )
            observer.on_loop_done("loop-live", "completed", 2)
            observer.on_sandbox_cleanup(kept=False, path=Path("/tmp/sbx_live"))

        output = buffer.getvalue()
        assert "/tmp/sbx_live" in output
        assert "Live Step" in output
        assert "echo live" in output
        assert "loop-live" in output
        assert "Conditions not met. Continuing to turn 2" in output
        assert "Sandbox: Cleaned" in output
