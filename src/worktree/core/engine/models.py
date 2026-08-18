"""Result types for the blueprint execution engine."""

from enum import StrEnum


class EngineResumeStatus(StrEnum):
    """Classified cannot-start outcomes for ``Engine.resume``."""

    NOT_FOUND = "not_found"
    WRONG_STATUS = "wrong_status"
    MISSING_SANDBOX = "missing_sandbox"
    CORRUPT_CHECKPOINT = "corrupt_checkpoint"
    FAILED = "failed"
