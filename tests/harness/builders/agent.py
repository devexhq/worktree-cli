"""Fluent agent response builder for Worktree CLI test suite."""

from __future__ import annotations

from typing import Self

from tests.harness.matchers import ANY_DURATION_MS, AnyMatching, AnyValue
from worktree.core.agents import AgentResponse, AgentResponseStatus


class AgentResponseBuilder:
    """Fluent builder for constructing expected AgentResponse models in tests.

    Defaults ``duration_ms`` to ``ANY_DURATION_MS``: every ``AgentResponse`` in this
    suite is produced by code that stamps real ``time.monotonic()`` elapsed time, so no
    test can own an exact value for it.
    """

    def __init__(self) -> None:
        self._status: AgentResponseStatus = AgentResponseStatus.NO_OP
        self._unified_diff: str | AnyMatching | None = None
        self._summary: str | None = None
        self._unfixable_reason: str | None = None
        self._raw_text: str | None = None
        self._duration_ms: AnyValue = ANY_DURATION_MS
        self._errors: list[str] = []
        self._mutation_baseline_ref: str | AnyMatching | None = None

    def with_status(self, status: AgentResponseStatus) -> Self:
        """Set the normalized outcome status."""
        self._status = status
        return self

    def with_unified_diff(self, diff: str | AnyMatching | None) -> Self:
        """Set the proposed unified diff text."""
        self._unified_diff = diff
        return self

    def with_summary(self, summary: str | None) -> Self:
        """Set the provider's human-readable summary."""
        self._summary = summary
        return self

    def with_unfixable_reason(self, reason: str | None) -> Self:
        """Set the reason the provider declared the failure unfixable."""
        self._unfixable_reason = reason
        return self

    def with_raw_text(self, raw_text: str | None) -> Self:
        """Set the raw provider output text."""
        self._raw_text = raw_text
        return self

    def with_errors(self, *errors: str) -> Self:
        """Append expected error messages."""
        self._errors.extend(errors)
        return self

    def with_baseline_ref(self, ref: str | AnyMatching | None) -> Self:
        """Set the expected sandbox git baseline ref."""
        self._mutation_baseline_ref = ref
        return self

    def build(self) -> AgentResponse:
        """Assemble and return the complete AgentResponse."""
        return AgentResponse.model_construct(
            status=self._status,
            unified_diff=self._unified_diff,
            summary=self._summary,
            unfixable_reason=self._unfixable_reason,
            raw_text=self._raw_text,
            duration_ms=self._duration_ms,
            errors=list(self._errors),
            mutation_baseline_ref=self._mutation_baseline_ref,
        )
