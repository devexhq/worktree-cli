"""Tests for the shared direct-mutation agent adapter base."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.harness import ANY_GIT_SHA, ANY_UNIFIED_DIFF, AgentRequestBuilder, AgentResponseBuilder, assert_model_equal
from worktree.core.agents import AgentRequest, AgentResponseStatus
from worktree.core.agents.cli_mutation import (
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunFn,
    CliMutationRunRequest,
    CliMutationRunStatus,
    build_mutation_prompt,
)
from worktree.core.agents.mutation_git import MutationGitError


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
    def test_prompt_includes_payload(self, git_repo: Path) -> None:
        """Prompt is the fixed instructions header plus an exact literal JSON body."""
        request = AgentRequestBuilder().with_sandbox_path(git_repo).build()
        expected_body = {
            "mode": "fix_failure",
            "sandbox_path": str(git_repo),
            "payload": request.payload.model_dump(mode="json"),
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
    def test_proposed_patch(self, git_repo: Path) -> None:
        """A finished run whose diff clears the patch gate returns PROPOSED_PATCH."""
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "fixed\n"}))

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(git_repo).build())

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
        assert (git_repo / "a.txt").read_text(encoding="utf-8") == "fixed\n"

    def test_no_op_when_no_edits(self, git_repo: Path) -> None:
        """A finished run with an empty diff (no edits) returns NO_OP."""
        adapter = UnitTestAdapter(run_fn=_fake_run())

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(git_repo).build())

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.NO_OP)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .build(),
        )

    def test_timeout_labels_provider_name(self, git_repo: Path) -> None:
        """A timed-out run returns TIMEOUT with the concrete provider name in the fix hint."""
        adapter = UnitTestAdapter(run_fn=_fake_run(status="timeout"))

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(git_repo).build())

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

    def test_provider_error(self, git_repo: Path) -> None:
        """A run that errors returns PROVIDER_ERROR carrying the runner's error detail."""
        adapter = UnitTestAdapter(run_fn=_fake_run(status="error", error_detail="boom"))

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(git_repo).build())

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .with_errors("Agent provider error (AGENT_PROVIDER_ERROR): boom")
            .build(),
        )

    def test_gate_violation_discards_edits(self, git_repo: Path) -> None:
        """Edits touching more files than max_files are discarded back to baseline."""
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"README.md": "edit one\n", "b.txt": "edit two\n"}))

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(git_repo).with_max_files(1).build())

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .with_errors("Patch touches 2 files; max_files is 1.")
            .build(),
        )
        assert (git_repo / "README.md").read_text(encoding="utf-8") == "# Test Repo\n"
        assert not (git_repo / "b.txt").exists()

    def test_gate_violation_discard_git_error_appends_to_errors(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A discard() failure after a gate violation appends its detail onto gate errors."""
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "1\n", "b.txt": "2\n"}))

        def _fail_discard(*a: object, **k: object) -> None:
            raise MutationGitError("git reset failed: index locked")

        monkeypatch.setattr("worktree.core.agents.cli_mutation.discard_since", _fail_discard)

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(git_repo).with_max_files(1).build())

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

    def test_gate_violation_preserves_wip(self, git_repo: Path) -> None:
        """Discard restores pre-existing uncommitted WIP, not the last committed tip."""
        (git_repo / "a.txt").write_text("wip content\n", encoding="utf-8")
        adapter = UnitTestAdapter(run_fn=_fake_run(edits={"a.txt": "edit 1\n", "b.txt": "edit 2\n"}))

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(git_repo).with_max_files(1).build())

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_raw_text("done")
            .with_baseline_ref(ANY_GIT_SHA)
            .with_errors("Patch touches 2 files; max_files is 1.")
            .build(),
        )
        assert (git_repo / "a.txt").read_text(encoding="utf-8") == "wip content\n"
        assert not (git_repo / "b.txt").exists()

    def test_preflight_blocks_before_baseline(self, git_repo: Path) -> None:
        """A failing _preflight short-circuits before baseline resolution or the runner call."""
        run_function_called = False

        def run_fn(request: CliMutationRunRequest) -> CliMutationOutcome:
            nonlocal run_function_called
            run_function_called = True
            return CliMutationOutcome(status="finished", result_text="nope")

        adapter = PreflightAdapter(run_fn=run_fn)

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(git_repo).build())

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_errors("Agent provider error (AGENT_PROVIDER_ERROR): preflight failed")
            .build(),
        )
        assert not run_function_called
