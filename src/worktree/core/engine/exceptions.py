"""Exceptions for the blueprint execution engine."""


class EngineError(Exception):
    """Base class for engine errors."""


class EngineRuntimeError(EngineError):
    """Raised when Engine cannot start a run."""
