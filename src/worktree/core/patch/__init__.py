"""Unified-diff validation (no git apply)."""

from worktree.core.patch.exceptions import MalformedDiffHeader
from worktree.core.patch.models import PatchApplyResult, PatchApplyStatus
from worktree.core.patch.patch import GitDiffParser, validate_patch_text

__all__ = [
    "GitDiffParser",
    "MalformedDiffHeader",
    "PatchApplyResult",
    "PatchApplyStatus",
    "validate_patch_text",
]
