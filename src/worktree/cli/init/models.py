"""Models for the init command."""

from __future__ import annotations

from worktree.core.bootstrap import WorkspaceInitResult


class InitCommandOutcome(WorkspaceInitResult):
    """Structured outcome returned by init command handler."""
