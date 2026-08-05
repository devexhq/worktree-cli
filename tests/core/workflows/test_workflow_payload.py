"""Tests for agent failure payload builder."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from getworktree.core.workflows.payload import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_TRIGGER_CHARS,
    AgentFailurePayload,
    build_failure_payload,
)
from getworktree.core.workflows.trigger import TriggerRunResult, TriggerRunStatus


def _trigger(
    *,
    status: TriggerRunStatus = TriggerRunStatus.FAILED,
    command: str = "pytest",
    args: list[str] | None = None,
    cwd: Path | None = None,
    exit_code: int | None = 1,
    timed_out: bool = False,
    stdout: str = "",
    stderr: str = "",
    duration_ms: int = 12,
) -> TriggerRunResult:
    return TriggerRunResult(
        status=status,
        command=command,
        args=list(args) if args is not None else ["-q"],
        cwd=cwd if cwd is not None else Path("/tmp/sandbox"),
        exit_code=exit_code,
        timed_out=timed_out,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "pkg").mkdir()
    (root / "pkg" / "mod.py").write_text("print('mod')\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(
        "def test_x():\n    assert False\n", encoding="utf-8"
    )
    return root


class BuildFailurePayloadTests:
    """Unit tests for build_failure_payload include tokens and guards."""

    def test_empty_include_identity_only(self, sandbox: Path) -> None:
        trigger = _trigger(
            cwd=sandbox,
            stdout="pkg/mod.py:1: error",
            stderr="boom",
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=[],
            changed_files=["pkg/mod.py"],
        )
        assert payload.command == "pytest"
        assert payload.args == ["-q"]
        assert payload.trigger_status == "failed"
        assert payload.exit_code == 1
        assert payload.timed_out is False
        assert payload.duration_ms == 12
        assert payload.stdout is None
        assert payload.stderr is None
        assert payload.stdout_truncated is False
        assert payload.stderr_truncated is False
        assert payload.changed_files == []
        assert payload.files == []
        assert payload.omissions == []

    def test_trigger_output_include_and_truncation(self, sandbox: Path) -> None:
        long_out = ("x" * 80) + ("Z" * 20)
        long_err = ("y" * 30) + ("E" * 20)
        trigger = _trigger(cwd=sandbox, stdout=long_out, stderr=long_err)
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["trigger_output"],
            max_trigger_chars=20,
        )
        assert payload.stdout is not None
        assert payload.stderr is not None
        assert payload.stdout_truncated is True
        assert payload.stderr_truncated is True
        # Keep the tail (failure details are usually at the end).
        assert payload.stdout.startswith("...[truncated, original_chars=100]")
        assert payload.stdout.endswith("Z" * 20)
        assert payload.stderr.startswith("...[truncated, original_chars=50]")
        assert payload.stderr.endswith("E" * 20)
        assert payload.files == []

    def test_trigger_output_no_truncation_under_cap(self, sandbox: Path) -> None:
        trigger = _trigger(cwd=sandbox, stdout="ok", stderr="")
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["trigger_output"],
            max_trigger_chars=80_000,
        )
        assert payload.stdout == "ok"
        assert payload.stderr == ""
        assert payload.stdout_truncated is False
        assert payload.stderr_truncated is False

    def test_changed_files_include(self, sandbox: Path) -> None:
        trigger = _trigger(cwd=sandbox)
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["changed_files"],
            changed_files=["pkg/mod.py", "tests/test_mod.py"],
        )
        assert payload.changed_files == ["pkg/mod.py", "tests/test_mod.py"]
        assert payload.files == []

    def test_changed_files_none_is_empty(self, sandbox: Path) -> None:
        payload = build_failure_payload(
            trigger=_trigger(cwd=sandbox),
            sandbox_path=sandbox,
            include=["changed_files"],
            changed_files=None,
        )
        assert payload.changed_files == []

    def test_relevant_source_from_output_and_changed(self, sandbox: Path) -> None:
        trigger = _trigger(
            cwd=sandbox,
            stdout="FAILURE in tests/test_mod.py line 2\n",
            stderr="",
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["pkg/mod.py"],
        )
        paths = [f.path for f in payload.files]
        assert paths == ["pkg/mod.py", "tests/test_mod.py"]
        assert payload.files[0].content == "print('mod')\n"
        assert payload.files[0].truncated is False
        assert payload.omissions == []

    def test_relevant_source_deterministic_sort_and_max_files(
        self, sandbox: Path
    ) -> None:
        for name in ("a.py", "b.py", "c.py"):
            (sandbox / name).write_text(f"# {name}\n", encoding="utf-8")
        trigger = _trigger(
            cwd=sandbox,
            stdout="a.py b.py c.py\n",
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["relevant_source"],
            max_files=2,
        )
        assert [f.path for f in payload.files] == ["a.py", "b.py"]
        assert any(
            o.path == "c.py" and o.reason == "max_files" for o in payload.omissions
        )

    def test_missing_file_omission(self, sandbox: Path) -> None:
        trigger = _trigger(cwd=sandbox, stdout="missing_file.py:1: boom\n")
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["relevant_source"],
        )
        assert payload.files == []
        assert any(
            o.path == "missing_file.py" and o.reason == "missing"
            for o in payload.omissions
        )

    def test_directory_omission(self, sandbox: Path) -> None:
        # Path extraction won't pick directories; feed via changed_files.
        payload = build_failure_payload(
            trigger=_trigger(cwd=sandbox),
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["pkg"],
        )
        assert payload.files == []
        assert any(
            o.path == "pkg" and o.reason == "directory" for o in payload.omissions
        )

    def test_binary_omission(self, sandbox: Path) -> None:
        bin_path = sandbox / "blob.py"
        bin_path.write_bytes(b"abc\x00def")
        payload = build_failure_payload(
            trigger=_trigger(cwd=sandbox),
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["blob.py"],
        )
        assert payload.files == []
        assert any(
            o.path == "blob.py" and o.reason == "binary" for o in payload.omissions
        )

    def test_file_byte_truncation(self, sandbox: Path) -> None:
        big = sandbox / "big.py"
        big.write_text("a" * 1000, encoding="utf-8")
        payload = build_failure_payload(
            trigger=_trigger(cwd=sandbox),
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["big.py"],
            max_file_bytes=50,
        )
        assert len(payload.files) == 1
        assert payload.files[0].truncated is True
        assert len(payload.files[0].content.encode("utf-8")) == 50

    def test_outside_sandbox_absolute(self, sandbox: Path, tmp_path: Path) -> None:
        outside = tmp_path / "outside.py"
        outside.write_text("nope\n", encoding="utf-8")
        payload = build_failure_payload(
            trigger=_trigger(cwd=sandbox, stdout=f"{outside}:1: err\n"),
            sandbox_path=sandbox,
            include=["relevant_source"],
        )
        assert payload.files == []
        assert any(o.reason == "outside_sandbox" for o in payload.omissions)

    def test_symlink_escape_outside_sandbox(
        self, sandbox: Path, tmp_path: Path
    ) -> None:
        outside = tmp_path / "secret.py"
        outside.write_text("secret\n", encoding="utf-8")
        link = sandbox / "escape.py"
        link.symlink_to(outside)
        payload = build_failure_payload(
            trigger=_trigger(cwd=sandbox),
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["escape.py"],
        )
        assert payload.files == []
        assert any(
            o.path == "escape.py" and o.reason == "outside_sandbox"
            for o in payload.omissions
        )

    def test_duplicate_candidates_unique(self, sandbox: Path) -> None:
        trigger = _trigger(
            cwd=sandbox,
            stdout="pkg/mod.py pkg/mod.py\n",
            stderr="see pkg/mod.py\n",
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["pkg/mod.py"],
        )
        assert [f.path for f in payload.files] == ["pkg/mod.py"]

    def test_missing_sandbox_root(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone"
        trigger = _trigger(
            cwd=missing,
            stdout="pkg/mod.py:1: x\n",
            exit_code=1,
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=missing,
            include=["trigger_output", "relevant_source", "changed_files"],
            changed_files=["pkg/mod.py"],
        )
        assert payload.trigger_status == "failed"
        assert payload.stdout is not None
        assert "pkg/mod.py" in payload.stdout
        assert payload.changed_files == ["pkg/mod.py"]
        assert payload.files == []
        assert payload.omissions
        assert all(o.reason == "missing" for o in payload.omissions)

    def test_timeout_identity_fields(self, sandbox: Path) -> None:
        trigger = _trigger(
            status=TriggerRunStatus.TIMEOUT,
            exit_code=None,
            timed_out=True,
            cwd=sandbox,
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=[],
        )
        assert payload.trigger_status == "timeout"
        assert payload.exit_code is None
        assert payload.timed_out is True

    def test_all_includes_combined(self, sandbox: Path) -> None:
        trigger = _trigger(
            cwd=sandbox,
            stdout="failed tests/test_mod.py\n",
            stderr="hint\n",
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["trigger_output", "changed_files", "relevant_source"],
            changed_files=["pkg/mod.py"],
        )
        assert payload.stdout == "failed tests/test_mod.py\n"
        assert payload.stderr == "hint\n"
        assert payload.changed_files == ["pkg/mod.py"]
        assert {f.path for f in payload.files} == {"pkg/mod.py", "tests/test_mod.py"}

    def test_defaults_match_issue_caps(self) -> None:
        assert DEFAULT_MAX_TRIGGER_CHARS == 20_000
        assert DEFAULT_MAX_FILE_BYTES == 64_000
        assert DEFAULT_MAX_FILES == 20

    def test_single_failing_test_prefers_only_that_file(self, sandbox: Path) -> None:
        (sandbox / "other.py").write_text("print('other')\n", encoding="utf-8")
        trigger = _trigger(
            cwd=sandbox,
            stdout=(
                "=========================== FAILURES ===========================\n"
                "____________________________ test_x ____________________________\n"
                "tests/test_mod.py:2: in test_x\n"
                "    assert False\n"
                "FAILED tests/test_mod.py::test_x - assert False\n"
            ),
            stderr="",
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["pkg/mod.py", "other.py"],
        )
        assert [f.path for f in payload.files] == ["tests/test_mod.py"]
        assert payload.files[0].content == "def test_x():\n    assert False\n"

    def test_multiple_failing_tests_include_only_those_files(
        self, sandbox: Path
    ) -> None:
        (sandbox / "tests" / "test_other.py").write_text(
            "def test_y():\n    assert False\n", encoding="utf-8"
        )
        (sandbox / "noise.py").write_text("print('noise')\n", encoding="utf-8")
        trigger = _trigger(
            cwd=sandbox,
            stdout=(
                "FAILED tests/test_mod.py::test_x - assert False\n"
                "FAILED tests/test_other.py::test_y - assert False\n"
            ),
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["noise.py", "pkg/mod.py"],
        )
        assert [f.path for f in payload.files] == [
            "tests/test_mod.py",
            "tests/test_other.py",
        ]

    def test_no_failing_test_falls_back_to_paths_and_changed(
        self, sandbox: Path
    ) -> None:
        trigger = _trigger(
            cwd=sandbox,
            stdout="see pkg/mod.py for details\n",
        )
        payload = build_failure_payload(
            trigger=trigger,
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["tests/test_mod.py"],
        )
        assert [f.path for f in payload.files] == ["pkg/mod.py", "tests/test_mod.py"]

    def test_payload_model_forbids_extra(self) -> None:
        with pytest.raises(ValidationError):
            AgentFailurePayload(
                command="x",
                args=[],
                trigger_status="failed",
                exit_code=1,
                timed_out=False,
                unexpected=True,  # type: ignore[call-arg]
            )

    def test_does_not_mutate_sandbox(self, sandbox: Path) -> None:
        before = {
            p.relative_to(sandbox).as_posix(): p.stat().st_mtime_ns
            for p in sandbox.rglob("*")
            if p.is_file() and not p.is_symlink()
        }
        build_failure_payload(
            trigger=_trigger(cwd=sandbox, stdout="pkg/mod.py\n"),
            sandbox_path=sandbox,
            include=["relevant_source", "trigger_output", "changed_files"],
            changed_files=["pkg/mod.py"],
        )
        after = {
            p.relative_to(sandbox).as_posix(): p.stat().st_mtime_ns
            for p in sandbox.rglob("*")
            if p.is_file() and not p.is_symlink()
        }
        assert before == after
        # No temp junk
        assert not any(p.name.endswith(".tmp") for p in sandbox.rglob("*"))

    def test_relative_path_with_dot_segments(self, sandbox: Path) -> None:
        payload = build_failure_payload(
            trigger=_trigger(cwd=sandbox),
            sandbox_path=sandbox,
            include=["relevant_source"],
            changed_files=["./pkg/../pkg/mod.py"],
        )
        assert [f.path for f in payload.files] == ["pkg/mod.py"]
