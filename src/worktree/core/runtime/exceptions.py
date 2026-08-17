"""Exceptions for the shared multi-step runtime."""


class PromptUserInterruptedError(Exception):
    """Raised when an interactive prompt is interrupted after a checkpoint is saved."""
