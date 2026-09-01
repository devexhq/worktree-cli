"""Sandbox domain package."""

from .exceptions import (
    SandboxCapacityError,
    SandboxConfigError,
    SandboxError,
)
from .manager import GitSandboxManager
from .models import (
    PruneAction,
    PrunedItem,
    PrunedItemResult,
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxApplyStrategy,
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxDetectionResult,
    SandboxDetectionStatus,
    SandboxDiffResult,
    SandboxDiffStatus,
    SandboxPruneResult,
    SandboxPruneStatus,
    SandboxSession,
    StaleSandboxCategory,
    StaleSandboxItem,
)
from .services.detector import SandboxDetector, detect_stale_sandboxes
from .services.lifecycle import SandboxLifecycle
from .services.patch import SandboxPatch
from .services.pruner import SandboxPruner, prune_stale_sandboxes
from .services.wip import apply_wip_to_sandbox

__all__ = [
    "GitSandboxManager",
    "PruneAction",
    "PrunedItem",
    "PrunedItemResult",
    "SandboxApplyResult",
    "SandboxApplyStatus",
    "SandboxApplyStrategy",
    "SandboxCapacityError",
    "SandboxConfigError",
    "SandboxCreateResult",
    "SandboxCreateStatus",
    "SandboxDetectionResult",
    "SandboxDetectionStatus",
    "SandboxDetector",
    "SandboxDiffResult",
    "SandboxDiffStatus",
    "SandboxError",
    "SandboxLifecycle",
    "SandboxPatch",
    "SandboxPruneResult",
    "SandboxPruneStatus",
    "SandboxPruner",
    "SandboxSession",
    "StaleSandboxCategory",
    "StaleSandboxItem",
    "apply_wip_to_sandbox",
    "detect_stale_sandboxes",
    "prune_stale_sandboxes",
]
