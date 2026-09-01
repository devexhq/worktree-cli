"""Git worktree sandbox management and lifecycle."""

from worktree.core.sandbox.exceptions import (
    SandboxCapacityError,
    SandboxConfigError,
    SandboxError,
)
from worktree.core.sandbox.facade import Sandbox
from worktree.core.sandbox.models import (
    PruneAction,
    PrunedItem,
    SandboxApplyResult,
    SandboxApplyStatus,
    SandboxApplyStrategy,
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxDeleteResult,
    SandboxDeleteStatus,
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
from worktree.core.sandbox.services.delete import collect_sandbox_delete
from worktree.core.sandbox.services.detector import SandboxDetector, detect_stale_sandboxes
from worktree.core.sandbox.services.lifecycle import SandboxLifecycle
from worktree.core.sandbox.services.list import collect_sandbox_list
from worktree.core.sandbox.services.patch import SandboxPatch
from worktree.core.sandbox.services.pruner import SandboxPruner, prune_stale_sandboxes
from worktree.core.sandbox.services.show import collect_sandbox_show
from worktree.core.sandbox.services.wip import apply_wip_to_sandbox

__all__ = [
    "PruneAction",
    "PrunedItem",
    "Sandbox",
    "SandboxApplyResult",
    "SandboxApplyStatus",
    "SandboxApplyStrategy",
    "SandboxCapacityError",
    "SandboxConfigError",
    "SandboxCreateResult",
    "SandboxCreateStatus",
    "SandboxDeleteResult",
    "SandboxDeleteStatus",
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
    "collect_sandbox_delete",
    "collect_sandbox_list",
    "collect_sandbox_show",
    "detect_stale_sandboxes",
    "prune_stale_sandboxes",
]
