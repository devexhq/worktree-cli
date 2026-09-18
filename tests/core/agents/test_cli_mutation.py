"""Tests for the shared direct-mutation agent adapter base."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.harness import ANY_GIT_SHA, ANY_UNIFIED_DIFF, AgentResponseBuilder, assert_model_equal
from worktree.core.agents import AgentRequest, AgentResponseStatus
from worktree.core.agents.cli_mutation import (
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunFn,
    CliMutationRunRequest,
    CliMutationRunStatus,
    build_mutation_prompt,
)
from worktree.core.agents.models import AgentFailurePayload
from worktree.core.agents.mutation_git import MutationGitError


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


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    _git(["init"], cwd=root)
    _git(["config", "user.email", "test@example.com"], cwd=root)
    _git(["config", "user.name", "Test"], cwd=root)
    (root / "a.txt").write_text("original\n", encoding="utf-8")
    _git(["add", "-A"], cwd=root)
    _git(["commit", "-m", "init"], cwd=root)
    return root


def _fake_run(
    *,
    edits: dict[str, str] | None = None,
    status: CliMutationRunStatus = "finished",
    error_detail: str | None = None,
    result_text: str | None = "done",
) -> CliMutationRunFn:
    def _run(request: CliMutationRunRequest) -> CliMutationOutcome:
        if edits:
            for rel, content in edits.items():
                path = request.sandbox_path / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        return CliMutationOutcome(status=status, result_text=result_text, error_detail=error_detail)

    return _run


class UnitTestAdapter(CliDirectMutationAdapter):
    """Minimal concrete adapter exercising only the shared base's propose_fix flow."""

    def __init__(self, run_fn: CliMutationRunFn) -> None:
        self._run_fn = run_fn

    def _provider_name(self) -> str:
        return "unit-test"

    def _default_run(self, request: CliMutationRunRequest) -> CliMutationOutcome:
        return self._run_fn(request)


class PreflightAdapter(UnitTestAdapter):
    """Adapter double whose preflight always fails, to prove it blocks before baseline."""

    def _preflight(self, request: AgentRequest) -> str | None:
        return "preflight failed"


class SharedMutationPromptTests:
    def test_prompt_includes_payload(self, sandbox: Path) -> None:
        """Prompt is the fixed instructions header plus an exact literal JSON body."""
        request = _request(sandbox)
        expected_body = {
            "mode": "fix_failure",
            "sandbox_path": str(sandbox),
            "payload": _payload().model_dump(mode="json"),
        }
        expected = (
            "You are a coding agent running directly in this sandbox checkout. "
            "Fix the failure described below.\n"
            "- Make the smallest change that fixes the failure.\n"
            "- Stay inside this working directory; do not push, open a PR, or "
            "touch remotes.\n"
            "- Prefer leaving tests green.\n"
            "- Do not modify files under .worktree/.\n"
            "- When finished, leave the working tree containing only the fix.\n\n"
        ) + json.dumps(expected_body, indent=2, ensure_ascii=False)

        assert build_mutation_prompt(request) == expected


class SharedMutationAdapterTests:
    def test_proposed_patch(self, sandbox: Path) -> None:
        """A finished run whose diff clears the patch gate returns PROPOSED_PATCH."""
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "fixed\n"}))

        resp = adapter.propose_fix(_request(sandbox))

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROPOSED_PATCH)
            .with_unified_diff(ANY_UNIFIED_DIFF)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .build(),
        )
        assert resp.unified_diff is not None and "fixed" in resp.unified_diff
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "fixed\n"

    def test_no_op_when_no_edits(self, sandbox: Path) -> None:
        """A finished run with an empty diff (no edits) returns NO_OP."""
        adapter = UnitTestAdapter(run_fn=_fake_run())

        resp = adapter.propose_fix(_request(sandbox))

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.NO_OP)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .build(),
        )

    def test_timeout_labels_provider_name(self, sandbox: Path) -> None:
        """A timed-out run returns TIMEOUT with the concrete provider name in the fix hint."""
        adapter = UnitTestAdapter(run_fn=_fake_run(status="timeout"))

        resp = adapter.propose_fix(_request(sandbox))

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.TIMEOUT)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .with_errors(
                "Agent timed out after 10s (provider=unit-test).\nFix:\n- raise agent.timeout_seconds on the blueprint"
            )
            .build(),
        )

    def test_provider_error(self, sandbox: Path) -> None:
        """A run that errors returns PROVIDER_ERROR carrying the runner's error detail."""
        adapter = UnitTestAdapter(run_fn=_fake_run(status="error", error_detail="boom"))

        resp = adapter.propose_fix(_request(sandbox))

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .with_errors("Agent provider error (AGENT_PROVIDER_ERROR): boom")
            .build(),
        )

    def test_gate_violation_discards_edits(self, sandbox: Path) -> None:
        """Edits touching more files than max_files are discarded back to baseline."""
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "edit one\n", "b.txt": "edit two\n"}))

        resp = adapter.propose_fix(_request(sandbox, max_files=1))

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .with_errors("Patch touches 2 files; max_files is 1.")
            .build(),
        )
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "original\n"
        assert not (sandbox / "b.txt").exists()

    def test_gate_violation_discard_git_error_appends_to_errors(
        self, sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A discard() failure after a gate violation appends its detail onto gate errors."""
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "1\n", "b.txt": "2\n"}))

        def _fail_discard(*a: object, **k: object) -> None:
            raise MutationGitError("git reset failed: index locked")

        monkeypatch.setattr("worktree.core.agents.cli_mutation.discard_since", _fail_discard)

        resp = adapter.propose_fix(_request(sandbox, max_files=1))

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .with_errors(
                "Patch touches 2 files; max_files is 1.",
                "Agent provider error (AGENT_PROVIDER_ERROR): "
                "failed to discard rejected sandbox edit: git reset failed: index locked",
            )
            .build(),
        )

    def test_gate_violation_preserves_wip(self, sandbox: Path) -> None:
        """Discard restores pre-existing uncommitted WIP, not the last committed tip."""
        (sandbox / "a.txt").write_text("wip content\n", encoding="utf-8")
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "edit 1\n", "b.txt": "edit 2\n"}))

        resp = adapter.propose_fix(_request(sandbox, max_files=1))

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .with_errors("Patch touches 2 files; max_files is 1.")
            .build(),
        )
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "wip content\n"
        assert not (sandbox / "b.txt").exists()

    def test_preflight_blocks_before_baseline(self, sandbox: Path) -> None:
        """A failing _preflight short-circuits before baseline resolution or the runner call."""
        called = False

        def run_fn(request: CliMutationRunRequest) -> CliMutationOutcome:
            nonlocal called
            called = True
            return CliMutationOutcome(status="finished", result_text="nope")

        adapter = PreflightAdapter(run_fn=run_fn)

        resp = adapter.propose_fix(_request(sandbox))

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_errors("Agent provider error (AGENT_PROVIDER_ERROR): preflight failed")
            .build(),
        )
        assert not called
