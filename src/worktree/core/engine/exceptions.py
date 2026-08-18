"""Exceptions for the blueprint execution engine."""

from worktree.core.engine.models import EngineResumeStatus
from worktree.core.inputs import InputResolveResult


class EngineError(Exception):
    """Base class for engine errors."""


class EngineRuntimeError(EngineError):
    """Raised when Engine cannot start a run."""


class EngineInputError(EngineError):
    """Raised when Engine cannot resolve blueprint inputs."""

    def __init__(self, result: InputResolveResult) -> None:
        self.result = result
        if result.errors:
            message = result.errors[0]
        elif result.missing:
            message = f"Missing required input '{result.missing[0]}'."
        else:
            message = "Failed to resolve blueprint inputs."
        super().__init__(message)


class EngineResumeError(EngineError):
    """Raised when Engine cannot start a resume."""

    def __init__(self, status: EngineResumeStatus, message: str) -> None:
        self.status = status
        super().__init__(message)
