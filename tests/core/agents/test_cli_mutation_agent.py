"""Tests for the shared direct-mutation adapter base."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.agents import AgentRequest, AgentResponseStatus
from worktree.core.agents.cli_mutation import (
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunRequest,
    build_mutation_prompt,
)
from worktree.core.agents.models import AgentFailurePayload


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _payload() -> AgentFailurePayload:
    return AgentFailurePayload(
        command="pytest",
        args=["-q"],
        trigger_status="failed",
        exit_code=1,
        timed_out=False,
        duration_ms=10,
        stdout="boom",
        stderr="",
    )


def _request(sandbox: Path, **kwargs: object) -> AgentRequest:
    data: dict[str, object] = {
        "mode": "fix_failure",
        "payload": _payload(),
        "sandbox_path": sandbox,
        "timeout_seconds": 10,
    }
    data.update(kwargs)
    return AgentRequest.model_validate(data)


def _fake_run(
    *,
    edits: dict[str, str] | None = None,
    status: str = "finished",
    error_detail: str | None = None,
    result_text: str | None = "done",
):
    def _run(request: CliMutationRunRequest) -> CliMutationOutcome:
        if edits:
            for rel, content in edits.items():
                path = request.sandbox_path / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        return CliMutationOutcome(
            status=status,
            result_text=result_text,
            error_detail=error_detail,
        )

    return _run


@pytest.fixture
def sandbox(fs: FileSystem) -> Path:
    root = fs.base_path / "sandbox"
    root.mkdir()
    _git(["init"], cwd=root)
    _git(["config", "user.email", "test@example.com"], cwd=root)
    _git(["config", "user.name", "Test"], cwd=root)
    (root / "a.txt").write_text("original\n", encoding="utf-8")
    _git(["add", "-A"], cwd=root)
    _git(["commit", "-m", "init"], cwd=root)
    return root


class UnitTestAdapter(CliDirectMutationAdapter):
    def _provider_name(self) -> str:
        return "unit-test"

    def _default_run(self, request: CliMutationRunRequest) -> CliMutationOutcome:
        raise AssertionError("default run should not be used")


class PreflightAdapter(UnitTestAdapter):
    def _preflight(self, request: AgentRequest) -> str | None:
        return "preflight failed"


class SharedMutationPromptTests:
    def test_prompt_includes_payload(self, sandbox: Path) -> None:
        prompt = build_mutation_prompt(_request(sandbox))
        assert "fix_failure" in prompt
        assert "pytest" in prompt
        assert "boom" in prompt
        assert str(sandbox) in prompt


class SharedMutationAdapterTests:
    def test_proposed_patch(self, sandbox: Path) -> None:
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "fixed\n"}))

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROPOSED_PATCH
        assert resp.ok
        assert resp.unified_diff is not None
        assert "fixed" in resp.unified_diff
        assert resp.mutation_baseline_ref is not None
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "fixed\n"

    def test_no_op_when_no_edits(self, sandbox: Path) -> None:
        adapter = UnitTestAdapter(run_fn=_fake_run())

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.NO_OP
        assert resp.mutation_baseline_ref is not None

    def test_timeout_labels_provider_name(self, sandbox: Path) -> None:
        adapter = UnitTestAdapter(run_fn=_fake_run(status="timeout"))

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.TIMEOUT
        assert any("provider=unit-test" in err for err in resp.errors)
        assert resp.mutation_baseline_ref is not None

    def test_provider_error(self, sandbox: Path) -> None:
        adapter = UnitTestAdapter(run_fn=_fake_run(status="error", error_detail="boom"))

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("boom" in err for err in resp.errors)
        assert resp.mutation_baseline_ref is not None

    def test_gate_violation_discards_edits(self, sandbox: Path) -> None:
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "edit one\n", "b.txt": "edit two\n"}))

        resp = adapter.propose_fix(_request(sandbox, max_files=1))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("max_files" in err for err in resp.errors)
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "original\n"
        assert not (sandbox / "b.txt").exists()

    def test_preflight_blocks_before_baseline(self, sandbox: Path) -> None:
        called = False

        def run_fn(request: CliMutationRunRequest) -> CliMutationOutcome:
            nonlocal called
            called = True
            return CliMutationOutcome(status="finished", result_text="nope")

        adapter = PreflightAdapter(run_fn=run_fn)

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert resp.mutation_baseline_ref is None
        assert not called
        assert any("preflight failed" in err for err in resp.errors)
