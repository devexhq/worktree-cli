"""Fluent agent request builder for Worktree CLI test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from worktree.core.agents import AgentFailurePayload, AgentRequest


class AgentRequestBuilder:
    """Fluent builder for constructing AgentRequest inputs in tests."""

    def __init__(self) -> None:
        self._payload: AgentFailurePayload = AgentFailurePayload(
            command="pytest",
            args=["-q"],
            trigger_status="failed",
            exit_code=1,
            timed_out=False,
            duration_ms=10,
            stdout="boom",
            stderr="",
        )
        self._sandbox_path: Path | None = None
        self._timeout_seconds: int = 10
        self._model: str | None = None
        self._max_files: int | None = None

    def with_sandbox_path(self, sandbox_path: Path) -> Self:
        """Set the sandbox checkout the agent request runs against."""
        self._sandbox_path = sandbox_path
        return self

    def with_model(self, model: str) -> Self:
        """Set the provider model identifier."""
        self._model = model
        return self

    def with_max_files(self, max_files: int) -> Self:
        """Set the patch gate's max touched-files limit."""
        self._max_files = max_files
        return self

    def build(self) -> AgentRequest:
        """Assemble and return the complete AgentRequest."""
        if self._sandbox_path is None:
            raise ValueError("AgentRequestBuilder requires with_sandbox_path(...) before build()")
        return AgentRequest(
            mode="fix_failure",
            payload=self._payload,
            sandbox_path=self._sandbox_path,
            timeout_seconds=self._timeout_seconds,
            model=self._model,
            max_files=self._max_files,
        )
