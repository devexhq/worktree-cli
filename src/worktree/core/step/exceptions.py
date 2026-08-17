from worktree.common.exceptions import (
    DefinitionNotFoundError,
    DefinitionValidationError,
)


class StepNotFoundError(DefinitionNotFoundError):
    """Raised when a step definition file or ID cannot be found."""


class StepValidationError(DefinitionValidationError):
    """Raised when step definition YAML parsing or schema validation fails."""
