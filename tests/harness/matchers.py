"""Whole-object model equality assertion, plus matchers for values a test cannot own.

There is no `exclude` parameter. A field the test declines to pin is stated as a matcher
at the field's own position, which still pins the value's type or shape, and
`assert_model_equal` refuses an expected object that left any field to its default so a
waiver can never hide silently outside the comparison.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePath
from typing import Any, Final
from uuid import UUID

from pydantic import BaseModel


class AnyValue:
    """Matches any value of a given type, for a value the test cannot own."""

    __slots__ = ("_label", "_types")

    def __init__(self, types: type | tuple[type, ...], label: str) -> None:
        self._types = types
        self._label = label

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self._types)

    def __hash__(self) -> int:
        return hash(self._label)

    def __repr__(self) -> str:
        return self._label


class AnyMatching:
    """Matches any string fully matching a pattern, for shaped values like a git SHA."""

    __slots__ = ("_label", "_regex")

    def __init__(self, pattern: str, label: str) -> None:
        self._regex = re.compile(pattern)
        self._label = label

    def __eq__(self, other: object) -> bool:
        return isinstance(other, str) and self._regex.fullmatch(other) is not None

    def __hash__(self) -> int:
        return hash(self._label)

    def __repr__(self) -> str:
        return self._label


ANY_DATETIME: Final = AnyValue(datetime, "ANY_DATETIME")
ANY_UUID: Final = AnyValue(UUID, "ANY_UUID")
ANY_PATH: Final = AnyValue(PurePath, "ANY_PATH")
ANY_PID: Final = AnyValue(int, "ANY_PID")

# Full 40-hex only. A commit_sha in this repo comes from rev_parse and is always full length, and a
# {7,40} range would accept an abbreviated SHA the contract never produces. Add ANY_SHORT_GIT_SHA
# if an abbreviated form ever becomes a contract; do not loosen this one.
ANY_GIT_SHA: Final = AnyMatching(r"[0-9a-f]{40}", "ANY_GIT_SHA")

# created_at and updated_at are str, not datetime: _now_utc_str() in core/db/models.py formats
# "%Y-%m-%d %H:%M:%S". ANY_DATETIME would (correctly) fail against them, so match the format.
ANY_TIMESTAMP: Final = AnyMatching(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "ANY_TIMESTAMP")

# SandboxSession.created_at is str too, but sandbox/services/lifecycle.py stamps it with
# datetime.now(UTC).isoformat() rather than _now_utc_str(), so it carries microseconds and a
# UTC offset instead of the SQLite-style format ANY_TIMESTAMP matches.
ANY_ISO_TIMESTAMP: Final = AnyMatching(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?\+00:00", "ANY_ISO_TIMESTAMP")

# Wall-clock elapsed seconds from time.monotonic() around a real subprocess. No injectable clock
# sits at this seam (StepExecution times an actual OS process), so the value is unownable like a pid.
ANY_DURATION: Final = AnyValue(float, "ANY_DURATION")

# Deliberately absent: ANY_STR, ANY_INT, ANY_LIST. A string or number the test cannot own is
# almost always one the test should have constructed, and a broad matcher re-opens the hole
# `exclude` left. Add a narrow AnyMatching instead of widening this set.


def assert_model_equal(actual: BaseModel, expected: BaseModel, *, _path: str = "") -> None:
    """Compare two models field by field, requiring expected to name every field.

    Build expected with model_construct when it carries a matcher: the plain constructor
    validates and rejects one.
    """
    if type(actual) is not type(expected):
        raise AssertionError(f"type mismatch: {type(actual).__name__} != {type(expected).__name__}")

    fields = type(expected).model_fields
    unset = set(fields) - expected.model_fields_set
    if unset:
        raise AssertionError(
            f"expected object left {sorted(unset)} to defaults at {_path or '<root>'}; "
            "name every field so a changed default cannot pass unnoticed"
        )

    mismatches: list[str] = []
    for name in fields:
        actual_value = getattr(actual, name)
        expected_value = getattr(expected, name)
        if isinstance(expected_value, BaseModel):
            assert_model_equal(actual_value, expected_value, _path=f"{_path}{name}.")
        elif _is_model_sequence(expected_value):
            _assert_model_sequence_equal(actual_value, expected_value, f"{_path}{name}")
        elif actual_value != expected_value:
            mismatches.append(f"  {_path}{name}: {actual_value!r} != {expected_value!r}")

    if mismatches:
        raise AssertionError("model mismatch:\n" + "\n".join(mismatches))


def _is_model_sequence(value: object) -> bool:
    return isinstance(value, (list, tuple)) and any(isinstance(item, BaseModel) for item in value)


def _assert_model_sequence_equal(actual: Any, expected: Any, path: str) -> None:
    if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
        raise AssertionError(f"{path}: length mismatch, {actual!r} != {expected!r}")
    for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=True)):
        if isinstance(expected_item, BaseModel):
            assert_model_equal(actual_item, expected_item, _path=f"{path}[{index}].")
        elif actual_item != expected_item:
            raise AssertionError(f"{path}[{index}]: {actual_item!r} != {expected_item!r}")


# --------------------------------------------------------------------------------------------- #
# Usage
# --------------------------------------------------------------------------------------------- #
#
# Preferred: own the non-determinism at the seam (TEST-011), then compare literal values with the
# plain constructor. A virtual clock makes a timestamp deterministic, so no matcher is needed.
#
#     clock = VirtualClock(start=datetime(2026, 1, 1, tzinfo=UTC))
#     result = load_config(workspace, clock=clock)
#     assert_model_equal(
#         result,
#         ConfigLoadResult(
#             status=ConfigLoadStatus.INVALID,
#             config=None,
#             errors=["CONFIG_SCHEMA_INVALID: missing 'version'"],
#             loaded_at=datetime(2026, 1, 1, tzinfo=UTC),
#         ),
#     )
#
# Fallback: the value is genuinely unownable (a real git SHA, an OS pid, an id minted by the DB),
# so it is matched at its own field position. model_construct is required because the plain
# constructor rejects a matcher under strict=True.
#
#     assert_model_equal(
#         result,
#         SandboxCreateResult.model_construct(
#             status=CREATED,
#             sandbox_id=ANY_UUID,
#             head_sha=ANY_GIT_SHA,
#             worktree_path=tmp_path / "sandboxes" / "alpha",
#             created_at=ANY_DATETIME,
#             errors=[],
#         ),
#     )
#
# Banned, and no longer expressible: exclude={"errors"}. There is no exclude parameter. A field
# whose value the test declines to state must be stated as a matcher, which still pins its type.
#
# Two traps on SQLModel table models (SandboxRecord, RunRecord, CatalogRecord):
#   - model_construct bypasses __init__, so SandboxRecord's str-to-Path coercion does not run.
#     Pass sandbox_path as a real Path.
#   - Table models skip validation on __init__, so the plain constructor accepts a matcher where
#     a plain BaseModel would reject it; prefer model_construct anyway for consistency with the
#     BaseModel path.
