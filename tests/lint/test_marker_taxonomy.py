"""Tier 4 invariant: every test module carries exactly one primary marker (TEST-016)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

from tests.lint.astlib import REPO_ROOT, TESTS_ROOT, collect_python_files

pytestmark = pytest.mark.invariant

PRIMARY_MARKERS: Final[frozenset[str]] = frozenset({"unit", "integration", "cli", "invariant"})
_ADDITIVE_MARKERS: Final[frozenset[str]] = frozenset({"slow"})
_TESTS_LINT_PREFIX: Final[str] = "tests/lint/"
_BOUNDARY_KEYWORDS: Final[frozenset[str]] = frozenset({"git", "sqlite3", "subprocess", "lock"})

# Genuinely mismarked today (confirmed: integration marker, no git/sqlite/subprocess/lock
# reference anywhere in the file). Fixed by re-marking to `unit` in Phase 2 W2.4.
# Remove entries as each module is re-marked. Never add.
INTEGRATION_MARKER_BURN_DOWN: Final[frozenset[str]] = frozenset(
    {
        "tests/core/config/test_loader.py",
        "tests/core/config/test_mutate.py",
        "tests/core/catalog/test_catalog.py",
    }
)

# Correctly marked `integration` today; the boundary-keyword heuristic cannot see the real
# boundary because it is crossed inside an orchestrator the test imports, not via a direct
# git/sqlite3/subprocess/lock import in the test's own imports. Permanent unless the heuristic
# itself changes scope; distinct from INTEGRATION_MARKER_BURN_DOWN, which tracks real
# violations. Never treat an entry here as something Phase 2 needs to "fix."
#
# - test_loop_runner.py: LoopBlockRunner executes a StepType.COMMAND step.
# - test_runner_retry.py: StepExecution.run() spawns a real subprocess (sys.executable) for
#   retry-loop verification.
# - test_builders.py::WorkspaceBuilderTests: WorkspaceBuilder (tests/harness) initializes a
#   real git repository and a real sqlite database on disk.
INTEGRATION_HEURISTIC_EXEMPT: Final[frozenset[str]] = frozenset(
    {
        "tests/core/runtime/test_loop_runner.py",
        "tests/core/step/test_runner_retry.py",
        "tests/harness/test_builders.py",
    }
)

# Zero-marker or conflicting-marker modules known today. Fixed by adding the missing
# module- or class-level marker(s) in Phase 2 (extends W2.4's scope). Remove entries as each
# module gets its marker(s). Never add.
PRIMARY_MARKER_BURN_DOWN: Final[frozenset[str]] = frozenset(
    {
        "tests/harness/test_harness_primitives.py",
    }
)


def _is_test_class_name(name: str) -> bool:
    """Match pytest's configured python_classes collection pattern (Test*, *Tests)."""
    return name.startswith("Test") or name.endswith("Tests")


def _extract_marker_names(expr: ast.expr) -> list[str]:
    """Resolve pytest.mark.<name> attribute(s) from a pytestmark or decorator expression.

    Args:
        expr: The assigned value (module-level pytestmark) or decorator expression
            (class-level @pytest.mark.<name>).

    Returns:
        Bare marker names found, in source order. Empty when expr isn't a pytest.mark.* shape.
    """
    if isinstance(expr, (ast.List, ast.Tuple)):
        names: list[str] = []
        for elt in expr.elts:
            names.extend(_extract_marker_names(elt))
        return names

    if (
        isinstance(expr, ast.Attribute)
        and isinstance(expr.value, ast.Attribute)
        and expr.value.attr == "mark"
        and isinstance(expr.value.value, ast.Name)
        and expr.value.value.id == "pytest"
    ):
        return [expr.attr]

    return []


def _declared_module_markers(tree: ast.Module) -> list[str]:
    """Extract marker names from a module-level pytestmark assignment."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        ):
            return _extract_marker_names(node.value)
    return []


def _declared_class_markers(class_node: ast.ClassDef) -> list[str]:
    """Extract marker names from a test class's decorator list."""
    names: list[str] = []
    for decorator in class_node.decorator_list:
        names.extend(_extract_marker_names(decorator))
    return names


def _primary_markers(names: list[str]) -> list[str]:
    """Filter declared marker names down to primaries, dropping additive markers like slow."""
    return [name for name in names if name in PRIMARY_MARKERS]


def _test_classes(tree: ast.Module) -> list[ast.ClassDef]:
    """Collect top-level classes matching pytest's test-class collection pattern."""
    return [node for node in tree.body if isinstance(node, ast.ClassDef) and _is_test_class_name(node.name)]


def _check_module_marker_taxonomy(file_path: Path, rel_path: Path) -> list[str]:
    """Check one test module for exactly one primary marker, at module or class scope."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    module_markers = _primary_markers(_declared_module_markers(tree))

    if len(module_markers) == 1:
        return []
    if len(module_markers) > 1:
        return [f"{rel_path}: module declares conflicting primary markers {module_markers}"]

    test_classes = _test_classes(tree)
    if not test_classes:
        return [f"{rel_path}: no module-level primary marker and no test classes to carry one"]

    violations: list[str] = []
    for class_node in test_classes:
        class_markers = _primary_markers(_declared_class_markers(class_node))
        if len(class_markers) == 0:
            violations.append(f"{rel_path}::{class_node.name}: no primary marker declared")
        elif len(class_markers) > 1:
            violations.append(f"{rel_path}::{class_node.name}: conflicting primary markers {class_markers}")
    return violations


def _imported_module_names(tree: ast.Module) -> list[str]:
    """Collect the dotted module path of every `import` and `from ... import` in a module."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _source_references_real_boundary(tree: ast.Module) -> bool:
    """Check whether a test module imports a real subsystem boundary (git, sqlite3, subprocess, lock).

    Matches against dotted-path segments only (e.g. the `git` in `worktree.core.git.runner` or
    in `mutation_git`), never against an unrelated identifier merely imported from a module
    (e.g. `CatalogItemType`, `LoopBlockRunner` are names, not import paths, so they never reach
    this check).
    """
    for module in _imported_module_names(tree):
        segments = module.lower().split(".")
        if any(keyword in segment for segment in segments for keyword in _BOUNDARY_KEYWORDS):
            return True
    return False


def _check_integration_boundary(file_path: Path, rel_path: Path) -> list[str]:
    """Flag an `integration`-marked module/class with no real-boundary reference."""
    if str(rel_path) in INTEGRATION_MARKER_BURN_DOWN or str(rel_path) in INTEGRATION_HEURISTIC_EXEMPT:
        return []

    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    has_boundary = _source_references_real_boundary(tree)
    module_markers = _primary_markers(_declared_module_markers(tree))

    if "integration" in module_markers:
        if has_boundary:
            return []
        return [f"{rel_path}: marked integration with no git/sqlite3/subprocess/lock import"]

    violations: list[str] = []
    for class_node in _test_classes(tree):
        class_markers = _primary_markers(_declared_class_markers(class_node))
        if "integration" in class_markers and not has_boundary:
            violations.append(
                f"{rel_path}::{class_node.name}: marked integration with no git/sqlite3/subprocess/lock import"
            )
    return violations


def _check_invariant_marker_scope(file_path: Path, rel_path: Path) -> list[str]:
    """Flag the `invariant` marker declared anywhere outside tests/lint/."""
    if str(rel_path).startswith(_TESTS_LINT_PREFIX):
        return []

    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    declared = set(_declared_module_markers(tree))
    for class_node in _test_classes(tree):
        declared.update(_declared_class_markers(class_node))

    if "invariant" in declared:
        return [f"{rel_path}: invariant marker declared outside tests/lint/"]
    return []


class MarkerTaxonomyTests:
    """Tier 4 marker-taxonomy invariant tests (TEST-016)."""

    def test_every_test_module_declares_one_primary_marker(self) -> None:
        """Every collected test module resolves to exactly one primary marker."""
        all_files = [f for f in collect_python_files(TESTS_ROOT) if f.name.startswith("test_")]
        assert all_files, "collect_python_files(TESTS_ROOT) returned no test_*.py files"

        violations: list[str] = []
        for file_path in all_files:
            rel_path = file_path.relative_to(REPO_ROOT)
            if str(rel_path) in PRIMARY_MARKER_BURN_DOWN:
                continue
            violations.extend(_check_module_marker_taxonomy(file_path, rel_path))

        assert not violations, "Modules with zero or multiple primary markers:\n" + "\n".join(violations)

    def test_scanner_flags_module_with_zero_primary_markers(self, tmp_path: Path) -> None:
        """Regression: a module with no pytestmark and no class-level marker is flagged."""
        module_path = tmp_path / "test_sample.py"
        module_path.write_text("class SampleTests:\n    def test_thing(self) -> None:\n        assert True\n")
        violations = _check_module_marker_taxonomy(module_path, module_path)
        assert len(violations) == 1

    def test_scanner_flags_module_with_conflicting_primary_markers(self, tmp_path: Path) -> None:
        """Regression: pytestmark = [pytest.mark.unit, pytest.mark.cli] is flagged."""
        module_path = tmp_path / "test_sample.py"
        module_path.write_text(
            "import pytest\n"
            "pytestmark = [pytest.mark.unit, pytest.mark.cli]\n\n"
            "class SampleTests:\n"
            "    def test_thing(self) -> None:\n"
            "        assert True\n"
        )
        violations = _check_module_marker_taxonomy(module_path, module_path)
        assert len(violations) == 1

    def test_scanner_allows_class_level_markers_when_module_mixes_tiers(self, tmp_path: Path) -> None:
        """Positive: no module-level marker, one class-level primary marker per *Tests class."""
        module_path = tmp_path / "test_sample.py"
        module_path.write_text(
            "import pytest\n\n"
            "@pytest.mark.unit\n"
            "class FirstTests:\n"
            "    def test_a(self) -> None:\n"
            "        assert True\n\n"
            "@pytest.mark.integration\n"
            "class SecondTests:\n"
            "    def test_b(self) -> None:\n"
            "        assert True\n"
        )
        violations = _check_module_marker_taxonomy(module_path, module_path)
        assert violations == []

    def test_invariant_marker_used_only_under_tests_lint(self) -> None:
        """No module or class outside tests/lint/ declares the invariant marker."""
        all_files = [f for f in collect_python_files(TESTS_ROOT) if f.name.startswith("test_")]
        assert all_files, "collect_python_files(TESTS_ROOT) returned no test_*.py files"

        violations: list[str] = []
        for file_path in all_files:
            rel_path = file_path.relative_to(REPO_ROOT)
            violations.extend(_check_invariant_marker_scope(file_path, rel_path))

        assert not violations, "invariant marker declared outside tests/lint/:\n" + "\n".join(violations)

    def test_scanner_flags_invariant_marker_outside_tests_lint(self, tmp_path: Path) -> None:
        """Regression: invariant marker declared under a non-tests/lint path is flagged."""
        module_path = tmp_path / "test_sample.py"
        module_path.write_text(
            "import pytest\npytestmark = pytest.mark.invariant\n\n"
            "class SampleTests:\n"
            "    def test_thing(self) -> None:\n"
            "        assert True\n"
        )
        fake_rel_path = Path("tests/core/test_fake.py")
        violations = _check_invariant_marker_scope(module_path, fake_rel_path)
        assert len(violations) == 1

    def test_integration_modules_touch_a_real_boundary(self) -> None:
        """Every integration-marked module or class references a real subsystem boundary."""
        all_files = [f for f in collect_python_files(TESTS_ROOT) if f.name.startswith("test_")]
        assert all_files, "collect_python_files(TESTS_ROOT) returned no test_*.py files"

        violations: list[str] = []
        for file_path in all_files:
            rel_path = file_path.relative_to(REPO_ROOT)
            violations.extend(_check_integration_boundary(file_path, rel_path))

        assert not violations, "integration modules with no real-boundary reference:\n" + "\n".join(violations)

    def test_scanner_flags_integration_module_with_no_boundary_reference(self, tmp_path: Path) -> None:
        """Regression: catches the test_loader.py-shaped defect (tmp_path JSON only)."""
        module_path = tmp_path / "test_sample.py"
        module_path.write_text(
            "import pytest\npytestmark = pytest.mark.integration\n\n"
            "class SampleTests:\n"
            "    def test_thing(self, tmp_path) -> None:\n"
            "        (tmp_path / 'config.json').write_text('{}')\n"
        )
        violations = _check_integration_boundary(module_path, module_path)
        assert len(violations) == 1

    def test_scanner_flags_module_where_boundary_keyword_is_only_a_substring(self, tmp_path: Path) -> None:
        """Regression: `CatalogItemType`/`LoopBlockRunner`-shaped identifiers must not be
        mistaken for a real git/lock import (the false-negative found in review round 1)."""
        module_path = tmp_path / "test_sample.py"
        module_path.write_text(
            "import pytest\n"
            "from worktree.core.db import CatalogItemType\n\n"
            "pytestmark = pytest.mark.integration\n\n"
            "class SampleTests:\n"
            "    def test_thing(self) -> None:\n"
            "        assert CatalogItemType\n"
        )
        violations = _check_integration_boundary(module_path, module_path)
        assert len(violations) == 1

    def test_scanner_allows_integration_module_referencing_subprocess(self, tmp_path: Path) -> None:
        """Positive: an integration module importing subprocess is not flagged."""
        module_path = tmp_path / "test_sample.py"
        module_path.write_text(
            "import pytest\nimport subprocess\n\npytestmark = pytest.mark.integration\n\n"
            "class SampleTests:\n"
            "    def test_thing(self) -> None:\n"
            "        subprocess.run(['true'], check=True)\n"
        )
        violations = _check_integration_boundary(module_path, module_path)
        assert violations == []
