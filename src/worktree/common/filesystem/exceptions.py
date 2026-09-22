"""Exceptions raised by common filesystem services."""


class InvalidGlobalRootError(ValueError):
    """Raised when the global Worktree root is itself a Git repository."""
