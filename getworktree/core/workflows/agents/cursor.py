"""Cursor SDK direct-mutation coding agent adapter."""

from __future__ import annotations

import os
import threading

from getworktree.core.workflows.agents.base import AgentRequest
from getworktree.core.workflows.agents.cli_mutation import (
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunFn,
    CliMutationRunRequest,
)

CURSOR_API_KEY_ENV = "CURSOR_API_KEY"


def resolve_cursor_api_key(env: dict[str, str] | None = None) -> str | None:
    """Resolve the Cursor API key from the environment."""
    environ = env if env is not None else os.environ
    key = environ.get(CURSOR_API_KEY_ENV)
    if key is None or not key.strip():
        return None
    return key.strip()


def default_cursor_run(request: CliMutationRunRequest) -> CliMutationOutcome:
    """Invoke the real Cursor SDK agent; lazily imported."""
    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
    except ImportError as exc:
        return CliMutationOutcome(
            status="error",
            error_detail=(f"cursor-sdk is not installed ({exc}). Fix: pip install getworktree[cursor]"),
        )

    api_key = resolve_cursor_api_key()
    if api_key is None:
        return CliMutationOutcome(
            status="error",
            error_detail=f"missing {CURSOR_API_KEY_ENV}",
        )

    outcome: dict[str, object] = {}

    def _run() -> None:
        try:
            with Agent.create(
                AgentOptions(
                    model=request.model,
                    api_key=api_key,
                    local=LocalAgentOptions(cwd=str(request.sandbox_path)),
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
        return CliMutationOutcome(status="timeout")

    exception = outcome.get("exception")
    if exception is not None:
        return CliMutationOutcome(status="error", error_detail=str(exception))

    result = outcome.get("result")
    if result is None:
        return CliMutationOutcome(status="error", error_detail="no run result")

    raw_status = str(getattr(result, "status", "error"))
    text = getattr(result, "result", None)
    text_str = text if isinstance(text, str) else None
    if raw_status == "finished":
        return CliMutationOutcome(status="finished", result_text=text_str)
    if raw_status in {"cancelled", "timeout"}:
        return CliMutationOutcome(status="timeout", result_text=text_str)
    if raw_status in {"error", "expired"}:
        return CliMutationOutcome(
            status="error",
            result_text=text_str,
            error_detail=text_str or raw_status,
        )
    return CliMutationOutcome(
        status="error",
        result_text=text_str,
        error_detail=f"unrecognized Cursor run status {raw_status!r}",
    )


class CursorAgentAdapter(CliDirectMutationAdapter):
    """Run the Cursor SDK coding agent directly against a sandbox checkout."""

    def __init__(self, *, run_fn: CliMutationRunFn | None = None) -> None:
        super().__init__(run_fn=run_fn)

    def _preflight(self, request: AgentRequest) -> str | None:
        model = request.model.strip() if request.model else ""
        if not model:
            return "cursor requires a non-empty model. Fix: set agent.model in .worktree/config.json"
        if resolve_cursor_api_key() is None:
            return f"missing {CURSOR_API_KEY_ENV}. Fix: export {CURSOR_API_KEY_ENV}=..."
        return None

    def _provider_name(self) -> str:
        return "cursor"

    def _default_run(self, request: CliMutationRunRequest) -> CliMutationOutcome:
        return default_cursor_run(request)
