"""Core task package for task blueprint models and catalog loading."""

from worktree.core.inputs import ParameterInput
from worktree.core.task.exceptions import TaskLoadError, TaskValidationError
from worktree.core.task.models import TaskDefinition

# Shared alias used by issue #161 docs/tests.
TaskInput = ParameterInput

__all__ = [
    "ParameterInput",
    "TaskDefinition",
    "TaskInput",
    "TaskLoadError",
    "TaskValidationError",
]
