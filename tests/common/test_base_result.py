"""Unit tests for worktree.common.models.BaseResult and subclass inheritance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from worktree.common.models import BaseResult, DefinitionResolutionResult
from worktree.common.schema_validation import ValidationResult
from worktree.core.blueprint.models import BlueprintRunResult
from worktree.core.bootstrap.models import BootstrapResult, WorkspaceInitResult
from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogListResult,
    CatalogResolveResult,
    CatalogScanResult,
    CatalogShowResult,
    CatalogSubdirectoryScanResult,
    SeedResult,
)
from worktree.core.config.generator import ConfigGenerationResult
from worktree.core.config.loader import ConfigLoadResult
from worktree.core.config.mutate import ConfigSetResult
from worktree.core.config.validate import ConfigValidationResult
from worktree.core.diff.models import DiffResult
from worktree.core.engine.models import ReconciliationResult
from worktree.core.history.models import HistoryListResult, HistoryShowResult
from worktree.core.inputs.models import InputResolveResult
from worktree.core.patch.models import PatchApplyResult
from worktree.core.sandbox.models import (
    SandboxApplyResult,
    SandboxCreateResult,
    SandboxDeleteResult,
    SandboxDetectionResult,
    SandboxDiffResult,
    SandboxListResult,
    SandboxPruneResult,
    SandboxShowResult,
)
from worktree.core.status.models import WorktreeStatusResult
from worktree.core.step.models import (
    AssertionResult,
    ConditionEvaluationResult,
    StepResult,
)

ALL_RESULT_CLASSES = [
    DefinitionResolutionResult,
    ValidationResult,
    BootstrapResult,
    WorkspaceInitResult,
    CatalogResolveResult,
    SeedResult,
    CatalogScanResult,
    CatalogSubdirectoryScanResult,
    CatalogListResult,
    CatalogShowResult,
    CatalogDeleteResult,
    CatalogCreateResult,
    ConfigValidationResult,
    ConfigLoadResult,
    ConfigGenerationResult,
    ConfigSetResult,
    DiffResult,
    ReconciliationResult,
    HistoryListResult,
    HistoryShowResult,
    InputResolveResult,
    PatchApplyResult,
    SandboxListResult,
    SandboxShowResult,
    SandboxCreateResult,
    SandboxApplyResult,
    SandboxDiffResult,
    SandboxDetectionResult,
    SandboxPruneResult,
    SandboxDeleteResult,
    WorktreeStatusResult,
    AssertionResult,
    ConditionEvaluationResult,
    StepResult,
    BlueprintRunResult,
]


class BaseResultTests:
    """Unit tests for the BaseResult base DTO."""

    def test_default_fields(self) -> None:
        result = BaseResult()
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []

    def test_explicit_fields(self) -> None:
        result = BaseResult(
            errors=["err1"],
            warnings=["warn1"],
            fixes=["fix1"],
        )
        assert result.errors == ["err1"]
        assert result.warnings == ["warn1"]
        assert result.fixes == ["fix1"]

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            BaseResult(extra_field="invalid")  # pyright: ignore[reportCallIssue]

    @pytest.mark.parametrize(
        "result_cls",
        [pytest.param(cls, id=cls.__name__) for cls in ALL_RESULT_CLASSES],
    )
    def test_all_result_dtos_inherit_from_base_result(self, result_cls: type) -> None:
        assert issubclass(result_cls, BaseResult)
