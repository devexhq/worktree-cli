"""Pure process/output assertion evaluators for step results.

Each function is side-effect-free, never raises for well-formed inputs, and
returns a list of failure strings (empty means the check passed). Callers that
inspect process output must pass ``combined_output`` built as stdout, a newline,
then stderr.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from os.path import commonprefix
from typing import Any

_PATH_NOT_FOUND = object()

# Truncation constants/helpers adapted from CPython's unittest.util
# (safe_repr / _shorten / _common_shorten_repr) so long failure values stay readable.
_MAX_LENGTH = 80
_PLACEHOLDER_LEN = 12
_MIN_BEGIN_LEN = 5
_MIN_END_LEN = 5
_MIN_COMMON_LEN = 5
_MIN_DIFF_LEN = _MAX_LENGTH - (_MIN_BEGIN_LEN + _PLACEHOLDER_LEN + _MIN_COMMON_LEN + _PLACEHOLDER_LEN + _MIN_END_LEN)


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


def _safe_repr(value: Any, *, short: bool = False) -> str:
    """Return ``repr(value)``, optionally hard-truncated when longer than ``_MAX_LENGTH``.

    Falls back to ``object.__repr__`` if ``repr`` raises. When ``short`` is true
    and the result exceeds ``_MAX_LENGTH``, keeps the first ``_MAX_LENGTH``
    characters and appends `` [truncated]...``.
    """
    try:
        result = repr(value)
    except Exception:
        result = object.__repr__(value)
    if not short or len(result) < _MAX_LENGTH:
        return result
    return result[:_MAX_LENGTH] + " [truncated]..."


def _shorten(text: str, prefix_len: int, suffix_len: int) -> str:
    """Collapse the middle of ``text`` into a ``[N chars]`` placeholder.

    Keeps ``prefix_len`` leading and ``suffix_len`` trailing characters. If the
    omitted span is not longer than ``_PLACEHOLDER_LEN``, returns ``text``
    unchanged (placeholder would not save space).
    """
    skip = len(text) - prefix_len - suffix_len
    if skip > _PLACEHOLDER_LEN:
        return f"{text[:prefix_len]}[{skip} chars]{text[len(text) - suffix_len :]}"
    return text


def _common_shorten_repr(left: Any, right: Any) -> tuple[str, str]:
    """Return paired reprs shortened around their first differing region.

    When either full ``repr`` is longer than ``_MAX_LENGTH``, shares a common
    shortened prefix and keeps a window of differing characters so failure
    messages stay comparable side-by-side (unittest-style).
    """
    left_repr = _safe_repr(left)
    right_repr = _safe_repr(right)
    max_len = max(len(left_repr), len(right_repr))
    if max_len <= _MAX_LENGTH:
        return left_repr, right_repr

    prefix = commonprefix([left_repr, right_repr])
    prefix_len = len(prefix)
    common_len = _MAX_LENGTH - (max_len - prefix_len + _MIN_BEGIN_LEN + _PLACEHOLDER_LEN)
    if common_len > _MIN_COMMON_LEN:
        shortened_prefix = _shorten(prefix, _MIN_BEGIN_LEN, common_len)
        return (
            shortened_prefix + left_repr[prefix_len:],
            shortened_prefix + right_repr[prefix_len:],
        )

    shortened_prefix = _shorten(prefix, _MIN_BEGIN_LEN, _MIN_COMMON_LEN)
    return (
        shortened_prefix + _shorten(left_repr[prefix_len:], _MIN_DIFF_LEN, _MIN_END_LEN),
        shortened_prefix + _shorten(right_repr[prefix_len:], _MIN_DIFF_LEN, _MIN_END_LEN),
    )


def _short_repr(value: Any) -> str:
    """Single-value repr truncated like unittest failure output."""
    return _safe_repr(value, short=True)


def _short_pair(actual: Any, expected: Any) -> tuple[str, str]:
    """Paired reprs shortened around the first differing region (unittest-style)."""
    return _common_shorten_repr(actual, expected)


def _compare_eq(actual: Any, value: Any, path: str) -> list[str]:
    if actual == value:
        return []
    actual_repr, expected_repr = _short_pair(actual, value)
    return [f"json_match: '{path}' was {actual_repr}, expected {expected_repr}"]


def _compare_neq(actual: Any, value: Any, path: str) -> list[str]:
    if actual != value:
        return []
    actual_repr, expected_repr = _short_pair(actual, value)
    return [f"json_match: '{path}' was {actual_repr}, expected not {expected_repr}"]


def _compare_contains(actual: Any, value: Any, path: str) -> list[str]:
    try:
        if value in actual:
            return []
    except TypeError:
        pass
    return [f"json_match: '{path}' does not contain {_short_repr(value)} (was {_short_repr(actual)})"]


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
    actual_repr, expected_repr = _short_pair(actual, value)
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
