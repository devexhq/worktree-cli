"""Sandbox services for lifecycle, detection, pruning, list, show, delete, and patch operations."""

from worktree.core.sandbox.services.delete import collect_sandbox_delete
from worktree.core.sandbox.services.detector import SandboxDetector
from worktree.core.sandbox.services.lifecycle import SandboxLifecycle
from worktree.core.sandbox.services.list import collect_sandbox_list
from worktree.core.sandbox.services.patch import SandboxPatch
from worktree.core.sandbox.services.pruner import SandboxPruner
from worktree.core.sandbox.services.show import collect_sandbox_show

__all__ = [
    "SandboxDetector",
    "SandboxLifecycle",
    "SandboxPatch",
    "SandboxPruner",
    "collect_sandbox_delete",
    "collect_sandbox_list",
    "collect_sandbox_show",
]
