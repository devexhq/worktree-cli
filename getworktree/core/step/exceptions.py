class StepNotFoundError(Exception):
    """Raised when a step definition file or ID cannot be found."""


class StepValidationError(Exception):
    """Raised when step definition YAML parsing or schema validation fails."""
