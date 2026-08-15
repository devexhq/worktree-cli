"""Pure assertion evaluators for step results.

Each function never raises for well-formed inputs and returns a list of failure
strings (empty means the check passed). Callers that inspect process output must
pass ``combined_output`` built as stdout, a newline, then stderr. File-system
evaluators resolve paths under ``sandbox_path`` and reject sandbox escapes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from getworktree.core.step.utils.assertion_helpers import short_pair, short_repr

_PATH_NOT_FOUND = object()


def evaluate_exit_code(expected: int | list[int], actual_exit_code: int) -> list[str]:
    """Return failure strings when ``actual_exit_code`` is not in ``expected``."""
    expected_list = expected if isinstance(expected, list) else [expected]
    if actual_exit_code in expected_list:
        return []
    return [f"exit_code: expected {expected_list!r}, got {actual_exit_code}"]


def evaluate_output_contains(required: str | list[str], combined_output: str) -> list[str]:
    """Return failure strings for each required substring missing from output."""
    required_list = required if isinstance(required, list) else [required]
    failures: list[str] = []
    for entry in required_list:
        if entry not in combined_output:
            failures.append(f"output_contains: substring '{entry}' not found in output")
    return failures


def evaluate_output_not_contains(forbidden: str | list[str], combined_output: str) -> list[str]:
    """Return failure strings for each forbidden substring found in output."""
    forbidden_list = forbidden if isinstance(forbidden, list) else [forbidden]
    failures: list[str] = []
    for entry in forbidden_list:
        if entry in combined_output:
            failures.append(f"output_not_contains: forbidden substring '{entry}' found in output")
    return failures


def evaluate_regex_match(pattern: str, combined_output: str) -> list[str]:
    """Return failure strings when ``pattern`` is invalid or does not match output."""
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return [f"regex_match: invalid regex pattern '{pattern}': {exc}"]
    if compiled.search(combined_output) is None:
        return [f"regex_match: pattern '{pattern}' did not match output"]
    return []


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _resolve_json_path(root: Any, path: str) -> Any:
    """Walk nested dict keys along ``path``. Return ``_PATH_NOT_FOUND`` if unresolved."""
    current = root
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _PATH_NOT_FOUND
        current = current[segment]
    return current


def _compare_eq(actual: Any, value: Any, path: str) -> list[str]:
    if actual == value:
        return []
    actual_repr, expected_repr = short_pair(actual, value)
    return [f"json_match: '{path}' was {actual_repr}, expected {expected_repr}"]


def _compare_neq(actual: Any, value: Any, path: str) -> list[str]:
    if actual != value:
        return []
    actual_repr, expected_repr = short_pair(actual, value)
    return [f"json_match: '{path}' was {actual_repr}, expected not {expected_repr}"]


def _compare_contains(actual: Any, value: Any, path: str) -> list[str]:
    try:
        if value in actual:
            return []
    except TypeError:
        pass
    return [f"json_match: '{path}' does not contain {short_repr(value)} (was {short_repr(actual)})"]


def _compare_ordered(
    actual: Any,
    value: Any,
    path: str,
    operator: str,
    predicate: Callable[[Any, Any], bool],
    expected_phrase: str,
) -> list[str]:
    if not _is_numeric(actual) or not _is_numeric(value):
        return [
            f"json_match: operator '{operator}' requires numeric values, "
            f"got {type(actual).__name__} and {type(value).__name__}"
        ]
    if predicate(actual, value):
        return []
    actual_repr, expected_repr = short_pair(actual, value)
    return [f"json_match: '{path}' was {actual_repr}, expected {expected_phrase} {expected_repr}"]


_JSON_MATCH_OPERATORS: dict[str, Callable[[Any, Any, str], list[str]]] = {
    "eq": _compare_eq,
    "neq": _compare_neq,
    "contains": _compare_contains,
    "gt": lambda actual, value, path: _compare_ordered(actual, value, path, "gt", lambda a, v: a > v, "greater than"),
    "gte": lambda actual, value, path: _compare_ordered(actual, value, path, "gte", lambda a, v: a >= v, "at least"),
    "lt": lambda actual, value, path: _compare_ordered(actual, value, path, "lt", lambda a, v: a < v, "less than"),
    "lte": lambda actual, value, path: _compare_ordered(actual, value, path, "lte", lambda a, v: a <= v, "at most"),
}


def evaluate_json_match(config: dict[str, Any], stdout: str) -> list[str]:
    """Parse stdout as JSON and check a dot-path value against an operator/value.

    Returns a single failure string on mismatch/error, or ``[]`` on success.
    Dot-paths walk nested mapping keys only (no list indexes).
    """
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return ["json_match: Invalid JSON output"]

    path = config["path"]
    actual = _resolve_json_path(parsed, path)
    if actual is _PATH_NOT_FOUND:
        return [f"json_match: JSON path '{path}' not found"]

    operator = config["operator"]
    comparator = _JSON_MATCH_OPERATORS.get(operator)
    if comparator is None:
        return [f"json_match: unsupported operator '{operator}'"]

    return comparator(actual, config["value"], path)


def _normalize_path_list(paths: str | list[str]) -> list[str]:
    return paths if isinstance(paths, list) else [paths]


def _sandbox_candidate(rel_path: str, sandbox_path: Path) -> Path | None:
    """Resolve ``rel_path`` under ``sandbox_path``, or ``None`` if it escapes the sandbox."""
    sandbox_resolved = sandbox_path.resolve()
    candidate = (sandbox_path / rel_path).resolve()
    try:
        candidate.relative_to(sandbox_resolved)
    except ValueError:
        return None
    return candidate


def evaluate_file_exists(paths: str | list[str], sandbox_path: Path) -> list[str]:
    """Return failures when each path is missing, a directory, or escapes the sandbox."""
    failures: list[str] = []
    for rel_path in _normalize_path_list(paths):
        candidate = _sandbox_candidate(rel_path, sandbox_path)
        if candidate is None:
            failures.append(f"file_exists: path '{rel_path}' escapes the worktree sandbox")
            continue
        if not candidate.exists():
            failures.append(f"file_exists: path '{rel_path}' does not exist")
        elif candidate.is_dir():
            failures.append(f"file_exists: path '{rel_path}' is a directory, not a file")
    return failures


def evaluate_file_not_exists(paths: str | list[str], sandbox_path: Path) -> list[str]:
    """Return failures when each path exists inside the sandbox or escapes it."""
    failures: list[str] = []
    for rel_path in _normalize_path_list(paths):
        candidate = _sandbox_candidate(rel_path, sandbox_path)
        if candidate is None:
            failures.append(f"file_not_exists: path '{rel_path}' escapes the worktree sandbox")
            continue
        if candidate.exists():
            failures.append(f"file_not_exists: path '{rel_path}' exists but must not")
    return failures


def evaluate_file_not_empty(paths: str | list[str], sandbox_path: Path) -> list[str]:
    """Return failures when each path is missing, a directory, empty, or escapes the sandbox."""
    failures: list[str] = []
    for rel_path in _normalize_path_list(paths):
        candidate = _sandbox_candidate(rel_path, sandbox_path)
        if candidate is None:
            failures.append(f"file_not_empty: path '{rel_path}' escapes the worktree sandbox")
            continue
        if not candidate.exists():
            failures.append(f"file_not_empty: path '{rel_path}' does not exist")
        elif candidate.is_dir():
            failures.append(f"file_not_empty: path '{rel_path}' is a directory, not a file")
        elif candidate.stat().st_size == 0:
            failures.append(f"file_not_empty: path '{rel_path}' is empty (0 bytes)")
    return failures
