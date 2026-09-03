"""Unit tests for worktree.common.models module."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from worktree.common.models import DefinitionResolutionResult, DefinitionResolutionStatus


class _Entry(BaseModel):
    name: str


class DefinitionResultTests:
    """Unit tests for DefinitionResolutionResult and status checks."""

    def test_ok_property_true_only_for_ok_status(self) -> None:
        result = DefinitionResolutionResult[_Entry](
            status=DefinitionResolutionStatus.OK,
            requested_name="my-task",
            resolved=_Entry(name="my-task"),
        )

        assert result.ok is True

    @pytest.mark.parametrize(
        "status",
        [
            DefinitionResolutionStatus.NOT_FOUND,
            DefinitionResolutionStatus.INVALID_NAME,
            DefinitionResolutionStatus.LOAD_ERROR,
            DefinitionResolutionStatus.DISCOVERY_FAILED,
        ],
    )
    def test_ok_property_false_for_non_ok_statuses(self, status: DefinitionResolutionStatus) -> None:
        result = DefinitionResolutionResult[_Entry](status=status, requested_name="missing")

        assert result.ok is False

    def test_defaults_for_optional_fields(self) -> None:
        result = DefinitionResolutionResult[_Entry](
            status=DefinitionResolutionStatus.NOT_FOUND,
            requested_name="missing",
        )

        assert result.resolved is None
        assert result.definition is None
        assert result.matches == []
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            DefinitionResolutionResult[_Entry](
                status=DefinitionResolutionStatus.OK,
                requested_name="my-task",
                unexpected="nope",
            )
