"""Exceptions for the blueprint execution engine."""

from worktree.core.engine.models import EngineResumeStatus


class EngineError(Exception):
    """Base class for engine errors."""


class EngineRuntimeError(EngineError):
    """Raised when Engine cannot start a run."""


class EngineResumeError(EngineError):
    """Raised when Engine cannot start a resume."""

    def __init__(self, status: EngineResumeStatus, message: str) -> None:
        self.status = status
        super().__init__(message)
