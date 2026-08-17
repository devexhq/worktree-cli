"""Core task package for task blueprint models and catalog loading."""

from worktree.core.inputs import ParameterInput
from worktree.core.task.exceptions import TaskLoadError, TaskValidationError
from worktree.core.task.models import TaskDefinition
from worktree.core.task.services import (
    format_task_resolve_failure,
    format_task_run_failure,
    resolve_and_load_task,
    run_task,
)

# Shared alias used by issue #161 docs/tests.
TaskInput = ParameterInput

__all__ = [
    "ParameterInput",
    "TaskDefinition",
    "TaskInput",
    "TaskLoadError",
    "TaskValidationError",
    "format_task_resolve_failure",
    "format_task_run_failure",
    "resolve_and_load_task",
    "run_task",
]
