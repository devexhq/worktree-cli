"""Small stateless helpers shared by the workflow iteration step functions.

Everything here is pure utility: config resolution, abort/event plumbing,
agent-input dump formatting, and the shared "retry or exhaust" decision.
Stateful per-run data lives in ``steps.py`` (``_WorkflowContext``); the top-level
orchestration lives in ``runner.py`` (``run_workflow_iteration``).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from getworktree.common.constants import GIT_SUBPROCESS_TIMEOUT_SECONDS
from getworktree.common.fs import atomic_write_text, get_session_dir
from getworktree.core.config.models import WorktreeConfig
from getworktree.core.git_sandbox import SandboxSession
from getworktree.core.workflows.models import WorkflowDefinition
from getworktree.core.workflows.runner_models import (
    IsAbortedFn,
    OnEventFn,
    StepOutcome,
    StopReason,
    WorkflowFinalStatus,
)
from getworktree.core.workflows.trigger import TriggerRunResult


def _advance_or_exhaust(
    attempt_idx: int,
    max_attempts: int,
    *,
    exhausted_status: WorkflowFinalStatus = WorkflowFinalStatus.FAILED,
    exhausted_reason: StopReason = StopReason.MAX_ATTEMPTS_EXHAUSTED,
) -> StepOutcome:
    """Decide whether to retry or stop after a non-terminal attempt failure.

    Collapses the repeated "if this was the last attempt, stop as failed;
    otherwise continue" pattern used after every non-terminal step outcome
    (agent unfixable-but-not-stopping, timeout/provider-error, empty diff,
    approval rejected, patch apply failure, patch applied with no attempts
    left to re-trigger).
    """
    if attempt_idx >= max_attempts:
        return StepOutcome(
            continue_workflow=False,
            final_status=exhausted_status,
            stop_reason=exhausted_reason,
            command_passed=False,
        )
    return StepOutcome(continue_workflow=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def resolve_max_attempts(
    *,
    workflow: WorkflowDefinition,
    config: WorktreeConfig,
    caller_max_attempts: int | None = None,
) -> int:
    """Resolve effective max attempts with hard-limit clamp.

    Precedence:
    ``caller_max_attempts`` → ``workflow.iteration.max_attempts`` →
    ``config.workflow.default_max_attempts``, then
    ``min(..., config.workflow.max_attempts_hard_limit)``.
    """
    if caller_max_attempts is not None:
        effective = caller_max_attempts
    else:
        effective = (
            workflow.iteration.max_attempts or config.workflow.default_max_attempts
        )
    return min(effective, config.workflow.max_attempts_hard_limit)


def default_list_changed_files(sandbox_path: Path) -> list[str]:
    """List sandbox-relative paths changed vs HEAD via ``git diff --name-only``."""
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(sandbox_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    lines = [line.strip().replace("\\", "/") for line in completed.stdout.splitlines()]
    return sorted({line for line in lines if line})


def _is_aborted(
    *,
    abort_event: threading.Event | None,
    is_aborted: IsAbortedFn | None,
) -> bool:
    if abort_event is not None and abort_event.is_set():
        return True
    if is_aborted is not None and is_aborted():
        return True
    return False


def _emit(
    on_event: OnEventFn | None,
    name: str,
    **payload: Any,
) -> None:
    if on_event is not None:
        on_event(name, payload)


def _trigger_summary(result: TriggerRunResult) -> str:
    return result.status.value


def _render_agent_input_dump(*, provider: str, request: Any) -> tuple[str, str]:
    """Return ``(suffix, content)`` for a provider-specific agent-input dump."""
    if provider in {"cursor", "gemini", "copilot"}:
        from getworktree.core.workflows.agents.cli_mutation import build_mutation_prompt

        return ("txt", build_mutation_prompt(request))
    if provider == "local":
        payload = request.model_dump(mode="json")
        return ("json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    if provider == "ollama":
        from getworktree.core.workflows.agents.ollama import (
            DEFAULT_MAX_TOKENS,
            DEFAULT_TEMPERATURE,
            build_ollama_messages,
            resolve_ollama_endpoint,
        )

        body_obj = {
            "model": request.model or "",
            "stream": False,
            "messages": build_ollama_messages(request),
            "options": {
                "temperature": (
                    float(request.temperature)
                    if request.temperature is not None
                    else DEFAULT_TEMPERATURE
                ),
                "num_predict": (
                    int(request.max_tokens)
                    if request.max_tokens is not None
                    else DEFAULT_MAX_TOKENS
                ),
            },
            "endpoint": resolve_ollama_endpoint(request.endpoint),
        }
        return ("json", json.dumps(body_obj, indent=2, ensure_ascii=False) + "\n")
    payload = request.model_dump(mode="json")
    return ("json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _dump_agent_input(
    *,
    provider: str,
    request: Any,
    dump_dir: Path,
    session_id: str,
    attempt: int,
) -> tuple[Path | None, str | None]:
    """Write one provider-specific agent-input dump file.

    Returns:
        Tuple of ``(path, error)`` where exactly one item is non-None.
    """
    suffix, content = _render_agent_input_dump(provider=provider, request=request)
    dump_root = dump_dir.expanduser().resolve()
    filename = f"wt-agent-prompt-{session_id}-attempt-{attempt:02d}.{suffix}"
    output_path = dump_root / filename

    try:
        dump_root.mkdir(parents=True, exist_ok=True)
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as exc:
        return (
            None,
            f"Failed to write agent input dump '{output_path}': {exc}",
        )

    return (output_path, None)


def capture_and_persist_diff(
    *,
    session: SandboxSession | None,
    cwd: Path,
    warnings: list[str],
) -> None:
    """Capture cumulative unified diff from sandbox and persist to diff.patch artifact.

    Records warnings in ``warnings`` if sandbox is missing/cleaned, diff capture fails,
    or session directory/file is unwritable. Never raises exceptions.
    """
    if session is None:
        return

    sandbox_path = session.sandbox_path
    if not sandbox_path.is_dir():
        warnings.append(f"Sandbox directory missing or cleaned: {sandbox_path}")
        return

    diff_text = ""
    try:
        subprocess.run(
            ["git", "add", "-N", "."],
            cwd=str(sandbox_path),
            capture_output=True,
            text=True,
            timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
        completed = subprocess.run(
            ["git", "diff", session.base_commit],
            cwd=str(sandbox_path),
            capture_output=True,
            text=True,
            timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            err_msg = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"exit code {completed.returncode}"
            )
            warnings.append(f"Git diff capture failed in sandbox: {err_msg}")
        else:
            diff_text = completed.stdout
    except Exception as exc:
        warnings.append(f"Git diff capture failed in sandbox: {exc}")

    session_dir = get_session_dir(cwd, session.session_id)
    diff_patch_path = session_dir / "diff.patch"
    try:
        atomic_write_text(diff_patch_path, diff_text)
    except Exception as exc:
        warnings.append(f"Failed to write diff artifact '{diff_patch_path}': {exc}")
