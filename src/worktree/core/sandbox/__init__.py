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
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxApplyStrategy,
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxDetectionResult,
    SandboxDetectionStatus,
    SandboxDiffResult,
    SandboxDiffStatus,
    SandboxListResult,
    SandboxListStatus,
    SandboxPruneResult,
    SandboxPruneStatus,
    SandboxSession,
    SandboxShowResult,
    SandboxShowStatus,
    StaleSandboxCategory,
    StaleSandboxItem,
)
from .services.detector import SandboxDetector, detect_stale_sandboxes
from .services.lifecycle import SandboxLifecycle
from .services.list import collect_sandbox_list
from .services.patch import SandboxPatch
from .services.pruner import SandboxPruner, prune_stale_sandboxes
from .services.show import collect_sandbox_show
from .services.wip import apply_wip_to_sandbox

__all__ = [
    "GitSandboxManager",
    "PruneAction",
    "PrunedItem",
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
    "SandboxListResult",
    "SandboxListStatus",
    "SandboxPatch",
    "SandboxPruneResult",
    "SandboxPruneStatus",
    "SandboxPruner",
    "SandboxSession",
    "SandboxShowResult",
    "SandboxShowStatus",
    "StaleSandboxCategory",
    "StaleSandboxItem",
    "apply_wip_to_sandbox",
    "collect_sandbox_list",
    "collect_sandbox_show",
    "detect_stale_sandboxes",
    "prune_stale_sandboxes",
]
