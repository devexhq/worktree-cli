"""Cursor SDK direct-mutation coding agent adapter."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from getworktree.core.agents.base import (
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
)
from getworktree.core.agents.local import _timeout_error
from getworktree.core.agents.mutation_git import (
    MutationGitError,
    capture_diff_since,
    discard_since,
    resolve_pre_agent_baseline,
)
from getworktree.core.loops.patch import PatchApplyStatus, validate_patch_text

CURSOR_API_KEY_ENV = "CURSOR_API_KEY"
DEFAULT_MAX_FILES = 30
DEFAULT_MAX_PATCH_KB = 1024
DEFAULT_REJECT_BINARY_CHANGES = True

CursorRunStatus = Literal["finished", "error", "cancelled", "expired", "timeout"]


class CursorRunRequest(BaseModel):
    """Normalized inputs for invoking the Cursor SDK agent run."""

    model_config = {"extra": "forbid", "strict": True}

    model: str
    api_key: str
    cwd: str
    prompt: str
    timeout_seconds: float


class CursorRunOutcome(BaseModel):
    """Normalized result from a Cursor SDK agent run."""

    model_config = {"extra": "forbid", "strict": True}

    status: CursorRunStatus
    result_text: str | None = None
    error_detail: str | None = None


CursorRunFn = Callable[[CursorRunRequest], CursorRunOutcome]


def _provider_error(detail: str) -> str:
    return f"Agent provider error (AGENT_PROVIDER_ERROR): {detail}"


def resolve_cursor_api_key(env: dict[str, str] | None = None) -> str | None:
    """Resolve the Cursor API key from the environment.

    Args:
        env: Optional environment mapping override for tests.

    Returns:
        The trimmed API key, or ``None`` when unset or blank.
    """
    environ = env if env is not None else os.environ
    key = environ.get(CURSOR_API_KEY_ENV)
    if key is None or not key.strip():
        return None
    return key.strip()


def build_cursor_prompt(request: AgentRequest) -> str:
    """Build the agent prompt from the mode and failure payload."""
    instructions = (
        "You are a coding agent running directly in this sandbox checkout. "
        "Fix the failure described below.\n"
        "- Make the smallest change that fixes the failure.\n"
        "- Stay inside this working directory; do not push, open a PR, or "
        "touch remotes.\n"
        "- Prefer leaving tests green.\n"
        "- Do not modify files under .worktree/.\n"
        "- When finished, leave the working tree containing only the fix.\n\n"
    )
    body = {
        "mode": request.mode,
        "sandbox_path": str(request.sandbox_path),
        "payload": request.payload.model_dump(mode="json"),
    }
    return instructions + json.dumps(body, indent=2, ensure_ascii=False)


def default_cursor_run(request: CursorRunRequest) -> CursorRunOutcome:
    """Invoke the real Cursor SDK agent; lazily imported.

    Runs the SDK call on a background thread so ``request.timeout_seconds``
    can be enforced with ``run.cancel()`` when the wait does not return in
    time.
    """
    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
    except ImportError as exc:
        return CursorRunOutcome(
            status="error",
            error_detail=(
                f"cursor-sdk is not installed ({exc}). "
                "Fix: pip install getworktree[cursor]"
            ),
        )

    outcome: dict[str, object] = {}

    def _run() -> None:
        try:
            with Agent.create(
                AgentOptions(
                    model=request.model,
                    api_key=request.api_key,
                    local=LocalAgentOptions(cwd=request.cwd),
                )
            ) as agent:
                run = agent.send(request.prompt)
                outcome["run"] = run
                outcome["result"] = run.wait()
        except Exception as exc:  # defensive: classify, never raise cross-thread
            outcome["exception"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=request.timeout_seconds)
    if thread.is_alive():
        run = outcome.get("run")
        if run is not None:
            try:
                run.cancel()  # type: ignore[attr-defined]
            except Exception:
                pass
        thread.join(timeout=5)
        return CursorRunOutcome(status="timeout")

    exception = outcome.get("exception")
    if exception is not None:
        return CursorRunOutcome(status="error", error_detail=str(exception))

    result = outcome.get("result")
    if result is None:
        return CursorRunOutcome(status="error", error_detail="no run result")
    raw_status = str(getattr(result, "status", "error"))
    text = getattr(result, "result", None)
    text_str = text if isinstance(text, str) else None
    if raw_status not in {"finished", "error", "cancelled", "expired"}:
        return CursorRunOutcome(
            status="error",
            error_detail=f"unrecognized Cursor run status '{raw_status}'",
        )
    return CursorRunOutcome(
        status=raw_status,  # type: ignore[arg-type]
        result_text=text_str,
        error_detail=None if raw_status == "finished" else (text_str or raw_status),
    )


class CursorAgentAdapter:
    """Run the Cursor SDK coding agent directly against a sandbox checkout."""

    def __init__(self, *, cursor_run: CursorRunFn | None = None) -> None:
        """Create an adapter.

        Args:
            cursor_run: Optional injectable SDK runner for tests.
        """
        self._cursor_run = cursor_run or default_cursor_run

    def propose_fix(self, request: AgentRequest) -> AgentResponse:
        """Run the Cursor agent in the sandbox; never raises for classified outcomes."""
        started = time.monotonic()

        model = request.model.strip() if request.model else ""
        if not model:
            return AgentResponse(
                status=AgentResponseStatus.PROVIDER_ERROR,
                duration_ms=_elapsed_ms(started),
                errors=[
                    _provider_error(
                        "cursor requires a non-empty model. "
                        "Fix: set agent.model in .worktree/config.json"
                    )
                ],
            )

        api_key = resolve_cursor_api_key()
        if api_key is None:
            return AgentResponse(
                status=AgentResponseStatus.PROVIDER_ERROR,
                duration_ms=_elapsed_ms(started),
                errors=[
                    _provider_error(
                        f"missing {CURSOR_API_KEY_ENV}. "
                        f"Fix: export {CURSOR_API_KEY_ENV}=..."
                    )
                ],
            )

        try:
            baseline = resolve_pre_agent_baseline(request.sandbox_path)
        except MutationGitError as exc:
            return AgentResponse(
                status=AgentResponseStatus.PROVIDER_ERROR,
                duration_ms=_elapsed_ms(started),
                errors=[_provider_error(f"failed to resolve sandbox baseline: {exc}")],
            )

        prompt = build_cursor_prompt(request)
        outcome = self._cursor_run(
            CursorRunRequest(
                model=model,
                api_key=api_key,
                cwd=str(request.sandbox_path),
                prompt=prompt,
                timeout_seconds=float(request.timeout_seconds),
            )
        )
        duration_ms = _elapsed_ms(started)

        if outcome.status in {"timeout", "cancelled"}:
            return AgentResponse(
                status=AgentResponseStatus.TIMEOUT,
                duration_ms=duration_ms,
                mutation_baseline_ref=baseline,
                raw_text=outcome.result_text,
                errors=[_timeout_error(request.timeout_seconds, provider="cursor")],
            )

        if outcome.status in {"error", "expired"}:
            detail = (
                outcome.error_detail
                or f"cursor run ended with status '{outcome.status}'"
            )
            return AgentResponse(
                status=AgentResponseStatus.PROVIDER_ERROR,
                duration_ms=duration_ms,
                mutation_baseline_ref=baseline,
                raw_text=outcome.result_text,
                errors=[_provider_error(detail)],
            )

        # finished
        try:
            diff, _ = capture_diff_since(request.sandbox_path, baseline)
        except MutationGitError as exc:
            return AgentResponse(
                status=AgentResponseStatus.PROVIDER_ERROR,
                duration_ms=duration_ms,
                mutation_baseline_ref=baseline,
                raw_text=outcome.result_text,
                errors=[_provider_error(f"failed to capture sandbox diff: {exc}")],
            )

        if not diff.strip():
            return AgentResponse(
                status=AgentResponseStatus.NO_OP,
                duration_ms=duration_ms,
                mutation_baseline_ref=baseline,
                raw_text=outcome.result_text,
            )

        gate = validate_patch_text(
            diff,
            max_files=request.max_files or DEFAULT_MAX_FILES,
            max_patch_kb=request.max_patch_kb or DEFAULT_MAX_PATCH_KB,
            reject_binary_changes=(
                request.reject_binary_changes
                if request.reject_binary_changes is not None
                else DEFAULT_REJECT_BINARY_CHANGES
            ),
            sandbox_path=request.sandbox_path,
        )
        if gate.status != PatchApplyStatus.CHECKED_OK:
            try:
                discard_since(request.sandbox_path, baseline)
            except MutationGitError as exc:
                gate.errors.append(
                    _provider_error(f"failed to discard rejected sandbox edit: {exc}")
                )
            return AgentResponse(
                status=AgentResponseStatus.PROVIDER_ERROR,
                duration_ms=duration_ms,
                mutation_baseline_ref=baseline,
                raw_text=outcome.result_text,
                errors=list(gate.errors),
            )

        return AgentResponse(
            status=AgentResponseStatus.PROPOSED_PATCH,
            unified_diff=diff,
            duration_ms=duration_ms,
            mutation_baseline_ref=baseline,
            raw_text=outcome.result_text,
        )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
