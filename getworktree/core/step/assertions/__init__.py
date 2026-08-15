"""Pure assertion evaluators for step results.

Public API is re-exported here so callers import from
``getworktree.core.step.assertions`` without knowing the internal split.
"""

from getworktree.core.step.assertions.aggregate import evaluate_assertions
from getworktree.core.step.assertions.filesystem import (
    evaluate_file_exists,
    evaluate_file_not_empty,
    evaluate_file_not_exists,
)
from getworktree.core.step.assertions.json_match import evaluate_json_match
from getworktree.core.step.assertions.process import (
    evaluate_exit_code,
    evaluate_output_contains,
    evaluate_output_not_contains,
    evaluate_regex_match,
)
from getworktree.core.step.models import AssertionResult

__all__ = [
    "AssertionResult",
    "evaluate_assertions",
    "evaluate_exit_code",
    "evaluate_file_exists",
    "evaluate_file_not_empty",
    "evaluate_file_not_exists",
    "evaluate_json_match",
    "evaluate_output_contains",
    "evaluate_output_not_contains",
    "evaluate_regex_match",
]
