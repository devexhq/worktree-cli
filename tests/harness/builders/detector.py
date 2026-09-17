"""Fluent sandbox detection result builder for Worktree CLI test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from tests.harness.matchers import AnyMatching, AnyValue
from worktree.core.sandbox.models import (
    SandboxDetectionResult,
    SandboxDetectionStatus,
    StaleSandboxCategory,
    StaleSandboxItem,
)


class DetectionResultBuilder:
    """Fluent builder for constructing expected SandboxDetectionResult models in tests."""

    def __init__(self) -> None:
        self._status: SandboxDetectionStatus = SandboxDetectionStatus.OK
        self._items: list[StaleSandboxItem] = []
        self._active_sandbox_count: int = 0
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._fixes: list[str] = []

    def with_status(self, status: SandboxDetectionStatus) -> Self:
        """Set execution outcome status."""
        self._status = status
        return self

    def with_active_sandbox_count(self, count: int) -> Self:
        """Set count of active sandboxes."""
        self._active_sandbox_count = count
        return self

    def with_item(
        self,
        *,
        category: StaleSandboxCategory,
        identifier: str | AnyMatching | AnyValue,
        path: Path | AnyMatching | AnyValue | None = None,
        branch_name: str | AnyMatching | AnyValue | None = None,
        session_id: str | AnyMatching | AnyValue | None = None,
        is_dirty: bool = False,
        dirty_file_count: int = 0,
        reason: str | AnyMatching | AnyValue = "",
    ) -> Self:
        """Append an expected stale sandbox item by field values."""
        item = StaleSandboxItem.model_construct(
            category=category,
            identifier=identifier,
            path=path,
            branch_name=branch_name,
            session_id=session_id,
            is_dirty=is_dirty,
            dirty_file_count=dirty_file_count,
            reason=reason,
        )
        self._items.append(item)
        return self

    def with_errors(self, *errors: str) -> Self:
        """Append expected error messages."""
        self._errors.extend(errors)
        return self

    def build(self) -> SandboxDetectionResult:
        """Assemble and return the complete SandboxDetectionResult."""
        return SandboxDetectionResult.model_construct(
            status=self._status,
            items=list(self._items),
            active_sandbox_count=self._active_sandbox_count,
            errors=list(self._errors),
            warnings=list(self._warnings),
            fixes=list(self._fixes),
        )
