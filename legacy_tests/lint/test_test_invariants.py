"""Tier 4 architectural invariants enforcing test configuration and pytestmark taxonomy."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final[Path] = Path(__file__).parent.parent.parent
TESTS_ROOT: Final[Path] = REPO_ROOT / "tests"
PYPROJECT_PATH: Final[Path] = REPO_ROOT / "pyproject.toml"

ALLOWED_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "unit",
        "integration",
        "cli",
        "invariant",
        "slow",
    }
)

pytestmark = pytest.mark.invariant


def test_pyproject_defines_allowed_markers() -> None:
    """Ensure pyproject.toml registers the approved marker taxonomy."""
    with open(PYPROJECT_PATH, "rb") as f:
        config = tomllib.load(f)

    markers_config = config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    registered = {m.split(":")[0].strip() for m in markers_config}

    missing = ALLOWED_MARKERS - registered
    assert not missing, f"pyproject.toml missing required pytest markers: {missing}"


def _extract_marker_from_node(val: ast.expr) -> list[str]:
    """Extract marker names from an ast expression."""
    if isinstance(val, ast.Attribute) and isinstance(val.value, ast.Attribute):
        return [val.attr]
    if isinstance(val, (ast.List, ast.Tuple)):
        return [elt.attr for elt in val.elts if isinstance(elt, ast.Attribute)]
    return []


def _check_assign_node(node: ast.Assign, test_file: Path) -> list[str]:
    """Check an assignment node for unregistered pytestmark markers."""
    is_pytestmark = any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)
    if not is_pytestmark:
        return []

    marker_names = _extract_marker_from_node(node.value)
    rel_path = test_file.relative_to(REPO_ROOT)
    return [
        f"{rel_path}:{node.lineno} uses unregistered marker '{m}'" for m in marker_names if m not in ALLOWED_MARKERS
    ]


def _check_test_file_markers(test_file: Path) -> list[str]:
    """Check a single test file for pytestmark violations."""
    tree = ast.parse(test_file.read_text(encoding="utf-8"), filename=str(test_file))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            violations.extend(_check_assign_node(node, test_file))
    return violations


def test_pytestmarks_use_valid_registered_markers() -> None:
    """Ensure any declared module-level pytestmark uses only registered markers."""
    violations: list[str] = []
    for test_file in TESTS_ROOT.rglob("test_*.py"):
        violations.extend(_check_test_file_markers(test_file))

    assert not violations, "Found unregistered pytestmark markers:\n" + "\n".join(violations)
