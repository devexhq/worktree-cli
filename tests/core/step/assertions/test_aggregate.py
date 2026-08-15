"""Unit tests for the aggregate assertion evaluator."""

from pathlib import Path

from getworktree.core.step.assertions import evaluate_assertions
from getworktree.core.step.models import AssertionResult, StepAssert
from tests.helpers import FileSystem


class TestEvaluateAssertions:
    def test_all_pass(self, fs: FileSystem) -> None:
        fs.write_file("out.txt", "payload")
        result = evaluate_assertions(
            StepAssert(
                exit_code=0,
                output_contains='"status": "ok"',
                output_not_contains="error",
                regex_match=r'"n":\s*1',
                json_match={"path": "n", "operator": "eq", "value": 1},
                file_exists="out.txt",
                file_not_exists="missing.txt",
                file_not_empty="out.txt",
            ),
            exit_code=0,
            stdout='{"status": "ok", "n": 1}',
            stderr="",
            sandbox_path=fs.base_path,
        )

        assert result == AssertionResult(passed=True, failed_conditions=[], message="")

    def test_single_key_failure(self, fs: FileSystem) -> None:
        result = evaluate_assertions(
            StepAssert(exit_code=0, output_contains="expected"),
            exit_code=0,
            stdout="actual",
            stderr="",
            sandbox_path=fs.base_path,
        )

        assert result.passed is False
        assert result.failed_conditions == [
            "output_contains: substring 'expected' not found in output",
        ]
        assert result.message == "output_contains: substring 'expected' not found in output"

    def test_multi_key_failure_preserves_order(self, fs: FileSystem) -> None:
        result = evaluate_assertions(
            StepAssert(
                exit_code=0,
                output_contains="need-this",
                file_exists="absent.txt",
            ),
            exit_code=2,
            stdout="other",
            stderr="err",
            sandbox_path=fs.base_path,
        )

        assert result.passed is False
        assert result.failed_conditions == [
            "exit_code: expected [0], got 2",
            "output_contains: substring 'need-this' not found in output",
            "file_exists: path 'absent.txt' does not exist",
        ]
        assert result.message == "\n".join(result.failed_conditions)

    def test_default_exit_code_when_unset(self, fs: FileSystem) -> None:
        pass_result = evaluate_assertions(
            StepAssert(),
            exit_code=0,
            stdout="",
            stderr="",
            sandbox_path=fs.base_path,
        )
        fail_result = evaluate_assertions(
            StepAssert(),
            exit_code=1,
            stdout="",
            stderr="",
            sandbox_path=Path(fs.base_path),
        )

        assert pass_result == AssertionResult(passed=True, failed_conditions=[], message="")
        assert fail_result.passed is False
        assert fail_result.failed_conditions == ["exit_code: expected [0], got 1"]
        assert fail_result.message == "exit_code: expected [0], got 1"

    def test_unset_optional_keys_are_not_evaluated(self, fs: FileSystem) -> None:
        result = evaluate_assertions(
            StepAssert(json_match={"path": "ok", "operator": "eq", "value": True}),
            exit_code=0,
            stdout='{"ok": true}',
            stderr="noise that would fail output_not_contains if called",
            sandbox_path=fs.base_path,
        )

        assert result.passed is True
        assert result.failed_conditions == []
