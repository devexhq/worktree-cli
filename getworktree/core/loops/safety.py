"""Safety tripwires for loop iteration (repeat failure, no-op, session timeout)."""

from __future__ import annotations

import hashlib
import re
import time

from pydantic import BaseModel, Field

REPEAT_FAILURE_THRESHOLD = 3
NO_OP_STREAK_THRESHOLD = 2
_TAIL_CHARS = 4000
_WS_RE = re.compile(r"\s+")


class SafetyState(BaseModel):
    """Mutable streak counters for one loop session."""

    model_config = {"extra": "forbid", "strict": True}

    consecutive_failure_signatures: int = 0
    last_failure_signature: str | None = None
    consecutive_agent_no_ops: int = 0
    session_started_monotonic: float = Field(default_factory=time.monotonic)


def _normalize_tail(text: str) -> str:
    """Collapse whitespace and keep the last ``_TAIL_CHARS`` characters."""
    if not text:
        return ""
    collapsed = _WS_RE.sub(" ", text).strip()
    if len(collapsed) <= _TAIL_CHARS:
        return collapsed
    return collapsed[-_TAIL_CHARS:]


def failure_signature(
    trigger_status: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
) -> str:
    """Return full sha256 hex of a canonical failure fingerprint.

    Canonical form:
    ``trigger_status|exit_code|stdout_tail|stderr_tail`` with tails normalized
    (whitespace collapsed, stripped, last 4000 chars).
    """
    code = "" if exit_code is None else str(exit_code)
    canonical = "|".join(
        [
            trigger_status,
            code,
            _normalize_tail(stdout),
            _normalize_tail(stderr),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_trigger_failure(
    state: SafetyState,
    *,
    signature: str,
    detect_repeat_failures: bool,
) -> str | None:
    """Update failure-signature streaks after a failed trigger.

    Args:
        state: Session safety tracker (mutated).
        signature: Result of :func:`failure_signature`.
        detect_repeat_failures: When False, streaks are not updated and never trip.

    Returns:
        ``repeat_failure_signature`` when threshold is met; otherwise ``None``.
    """
    if not detect_repeat_failures:
        return None

    if state.last_failure_signature == signature:
        state.consecutive_failure_signatures += 1
    else:
        state.last_failure_signature = signature
        state.consecutive_failure_signatures = 1

    if state.consecutive_failure_signatures >= REPEAT_FAILURE_THRESHOLD:
        return "repeat_failure_signature"
    return None


def record_trigger_success(state: SafetyState) -> None:
    """Reset failure-signature streak after a passing trigger."""
    state.consecutive_failure_signatures = 0
    state.last_failure_signature = None


def record_agent_status(state: SafetyState, agent_status: str) -> str | None:
    """Update no-op streak after an agent call.

    Returns:
        ``agent_no_op_streak`` when threshold is met; otherwise ``None``.
    """
    if agent_status == "no_op":
        state.consecutive_agent_no_ops += 1
        if state.consecutive_agent_no_ops >= NO_OP_STREAK_THRESHOLD:
            return "agent_no_op_streak"
        return None

    state.consecutive_agent_no_ops = 0
    return None


def session_timed_out(
    state: SafetyState,
    *,
    session_timeout_seconds: int | None,
    now_monotonic: float | None = None,
) -> bool:
    """Return True when session wall-clock budget is exhausted.

    ``session_timeout_seconds`` of ``None`` or ``<= 0`` disables the check.
    """
    if session_timeout_seconds is None or session_timeout_seconds <= 0:
        return False
    now = time.monotonic() if now_monotonic is None else now_monotonic
    elapsed = now - state.session_started_monotonic
    return elapsed >= session_timeout_seconds


def safety_stop_message(
    stop_reason: str, *, session_timeout_seconds: int | None = None
) -> str:
    """Human-readable semantic stop line for UX (not printed by core)."""
    if stop_reason == "repeat_failure_signature":
        return f"Stopped: repeated identical trigger failures ({REPEAT_FAILURE_THRESHOLD}x)"
    if stop_reason == "agent_no_op_streak":
        return "Stopped: agent returned no-op twice in a row"
    if stop_reason == "session_timeout":
        secs = session_timeout_seconds if session_timeout_seconds is not None else "?"
        return f"Stopped: session timeout ({secs}s)"
    if stop_reason == "user_abort":
        return "Stopped: aborted by user"
    return f"Stopped: {stop_reason}"
