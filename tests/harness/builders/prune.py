"""Fluent sandbox prune result builder for Worktree CLI test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from tests.harness.matchers import AnyMatching, AnyValue
from worktree.core.sandbox.models import (
    PruneAction,
    PrunedItem,
    SandboxPruneResult,
    SandboxPruneStatus,
    StaleSandboxCategory,
)


class PruneResultBuilder:
    """Fluent builder for constructing expected SandboxPruneResult models in tests."""

    def __init__(self) -> None:
        self._status: SandboxPruneStatus = SandboxPruneStatus.OK
        self._dry_run: bool = False
        self._force: bool = False
        self._items: list[PrunedItem] = []
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._fixes: list[str] = []

    def with_status(self, status: SandboxPruneStatus) -> Self:
        """Set execution outcome status."""
        self._status = status
        return self

    def with_dry_run(self, dry_run: bool = True) -> Self:
        """Set dry-run simulation mode flag."""
        self._dry_run = dry_run
        return self

    def with_force(self, force: bool = True) -> Self:
        """Set force deletion mode flag."""
        self._force = force
        return self

    def with_item(
        self,
        *,
        category: StaleSandboxCategory,
        identifier: str,
        action: PruneAction = PruneAction.PRUNED,
        path: Path | AnyMatching | AnyValue | None = None,
        branch_name: str | AnyMatching | AnyValue | None = None,
        session_id: str | AnyMatching | AnyValue | None = None,
        reason: str | AnyMatching | AnyValue = "",
        error: str | AnyMatching | AnyValue | None = None,
    ) -> Self:
        """Append an expected pruned item by field values."""
        item = PrunedItem.model_construct(
            category=category,
            identifier=identifier,
            action=action,
            path=path,
            branch_name=branch_name,
            session_id=session_id,
            reason=reason,
            error=error,
        )
        self._items.append(item)
        return self

    def with_errors(self, *errors: str) -> Self:
        """Append expected error messages."""
        self._errors.extend(errors)
        return self

    def build(self) -> SandboxPruneResult:
        """Assemble and return the complete SandboxPruneResult."""
        return SandboxPruneResult.model_construct(
            status=self._status,
            dry_run=self._dry_run,
            force=self._force,
            items=list(self._items),
            errors=list(self._errors),
            warnings=list(self._warnings),
            fixes=list(self._fixes),
        )
