"""Tier 4 invariant: tests assert whole Result objects instead of piecewise fields (TEST-007)."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from tests.lint.astlib import REPO_ROOT, TESTS_ROOT, collect_python_files, extract_target_names
from worktree.common.models import BaseResult

pytestmark = pytest.mark.invariant

_CLI_RUNNER_RESULT_ATTRS: Final[set[str]] = {
    "exit_code",
    "stdout",
    "stderr",
    "output",
}

# Files still carrying pre-rewrite piecewise-assertion style, found on the scanner's
# first correct (class-recursing) run. Remove entries as Phase 2 remediates each file.
# Never add an entry.
SCANNER_BURN_DOWN: frozenset[str] = frozenset(
    {
        "tests/cli/commands/test_catalog.py",
        "tests/core/catalog/test_catalog.py",
        "tests/core/runtime/test_loop_runner.py",
        "tests/core/sandbox/test_patch.py",
        "tests/core/sandbox/test_squash.py",
        "tests/core/step/test_process_group.py",
        "tests/core/step/test_runner_assertions.py",
        "tests/core/step/test_runner_retry.py",
        "tests/core/step/test_step.py",
    }
)


def _get_base_result_attributes() -> set[str]:
    """Dynamically query all fields and public attributes defined on BaseResult.

    Ensures newly added fields (e.g. ok_message) are automatically covered
    without maintaining a static string set.
    """
    attrs = {f for f in BaseResult.model_fields.keys() if not f.startswith("model_")}
    for name, member in inspect.getmembers(BaseResult):
        if (
            not name.startswith("_")
            and not name.startswith("model_")
            and (isinstance(member, property) or not callable(member))
        ):
            attrs.add(name)
    attrs.update({"status", "ok"})
    return attrs


def _is_result_variable_name(name: str) -> bool:
    """Check if variable identifier indicates an operation result."""
    lowered = name.lower()
    if lowered.startswith("result") or lowered.endswith("_result"):
        return True
    return lowered.startswith("res") and not lowered.startswith("resource")


def _is_result_call(expr: ast.AST | None) -> bool:
    """Check if AST expression is a call to a Result constructor."""
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    if isinstance(func, ast.Name):
        return func.id.endswith("Result")
    if isinstance(func, ast.Attribute):
        return func.attr.endswith("Result")
    return False


def _extract_result_assignment_targets(node: ast.AST) -> list[str]:
    """Extract variable names assigned from a *Result constructor call."""
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return []
    if not _is_result_call(node.value):
        return []
    return extract_target_names(node)


def _format_target_name(value_node: ast.AST) -> str:
    """Format target node expression for violation messaging."""
    if isinstance(value_node, ast.Name):
        return value_node.id
    if isinstance(value_node, ast.Call):
        func = value_node.func
        if isinstance(func, ast.Name):
            return f"{func.id}()"
        if isinstance(func, ast.Attribute):
            return f"{func.attr}()"
    return "result"


def _iter_body_functions(
    body: list[ast.stmt],
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Walk a statement body, yielding functions defined directly in it or in nested classes."""
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield stmt
        elif isinstance(stmt, ast.ClassDef):
            yield from _iter_body_functions(stmt.body)


def _iter_test_functions(
    tree: ast.Module,
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield every test function, including methods nested in *Tests classes."""
    yield from _iter_body_functions(tree.body)


def _is_prohibited_attribute_access(
    child: ast.Attribute,
    base_attrs: set[str],
    local_result_vars: set[str],
) -> bool:
    """Determine whether an attribute access in an assert statement violates TEST-007."""
    if child.attr in base_attrs:
        return True
    if not isinstance(child.value, ast.Name):
        return False
    var_name = child.value.id
    if _is_result_variable_name(var_name) or var_name in local_result_vars:
        return child.attr not in _CLI_RUNNER_RESULT_ATTRS
    return False


def _check_assert_in_scope(
    node: ast.Assert,
    rel_path: Path,
    base_attrs: set[str],
    local_result_vars: set[str],
    violations: list[str],
) -> None:
    """Check assert statement for prohibited attribute accesses on results."""
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and _is_prohibited_attribute_access(child, base_attrs, local_result_vars):
            target = _format_target_name(child.value)
            violations.append(
                f"{rel_path}:{child.lineno}: Prohibited piecewise assertion on '{target}.{child.attr}'. "
                "Use assert_model_equal(result, Expected(...)) or assert actual == expected per [TEST-007]."
            )


def _scan_function_for_result_assertions(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    rel_path: Path,
    base_attrs: set[str],
    violations: list[str],
) -> None:
    """Scan a single test function body for piecewise result assertions."""
    local_result_vars: set[str] = set()
    for node in ast.walk(func_node):
        local_result_vars.update(_extract_result_assignment_targets(node))
        if isinstance(node, ast.Assert):
            _check_assert_in_scope(node, rel_path, base_attrs, local_result_vars, violations)


def _scan_file_for_piecewise_result_assertions(
    file_path: Path,
    base_attrs: set[str],
    allowlist: frozenset[str],
) -> list[str]:
    """Report piecewise result-field assertions, skipping allowlisted burn-down files."""
    rel_path = file_path.relative_to(REPO_ROOT) if file_path.is_relative_to(REPO_ROOT) else file_path
    if str(rel_path) in allowlist:
        return []

    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations: list[str] = []

    for func_node in _iter_test_functions(tree):
        _scan_function_for_result_assertions(func_node, rel_path, base_attrs, violations)
    for node in tree.body:
        if isinstance(node, ast.Assert):
            _check_assert_in_scope(node, rel_path, base_attrs, set(), violations)

    return violations


class AssertionStyleTests:
    """Tier 4 whole-object-assertion invariant tests (TEST-007)."""

    def test_tests_never_assert_individual_result_fields(self) -> None:
        """Ensure test files use whole-object comparison instead of piecewise result assertions."""
        all_files = collect_python_files(TESTS_ROOT)
        assert all_files, "collect_python_files(TESTS_ROOT) returned no files"
        base_attrs = _get_base_result_attributes()
        violations: list[str] = []
        for file_path in all_files:
            if file_path.name == "test_assertion_style.py":
                continue
            violations.extend(_scan_file_for_piecewise_result_assertions(file_path, base_attrs, SCANNER_BURN_DOWN))

        assert not violations, "Found piecewise result assertions in tests:\n" + "\n".join(violations)

    def test_scanner_flags_piecewise_assertions_inside_test_classes(self, tmp_path: Path) -> None:
        """Regression: guards the tree.body-only scope bug that made CI-004 flag this scanner."""
        snippet = tmp_path / "test_sample.py"
        snippet.write_text(
            "class SampleTests:\n"
            "    def test_result1_ok(self):\n"
            "        result1 = get_result()\n"
            "        assert result1.ok is True\n"
            "    def test_result2_errors(self):\n"
            "        result2 = get_result()\n"
            "        assert result2.errors == []\n"
            "    def test_custom_step_id(self):\n"
            "        custom = StepResult()\n"
            "        assert custom.step_id == '1'\n"
            "    def test_any_var_status(self):\n"
            "        any_var = op()\n"
            "        assert any_var.status == 'ok'\n"
        )
        base_attrs = _get_base_result_attributes()
        violations = _scan_file_for_piecewise_result_assertions(snippet, base_attrs, allowlist=frozenset())
        assert len(violations) == 4

    def test_scanner_allows_cli_runner_result_attributes(self, tmp_path: Path) -> None:
        """res.exit_code from runner.invoke is not a domain result access."""
        snippet = tmp_path / "test_sample.py"
        snippet.write_text(
            "class SampleTests:\n"
            "    def test_invoke_exit_code(self):\n"
            "        res = runner.invoke(app, [])\n"
            "        assert res.exit_code == 0\n"
        )
        base_attrs = _get_base_result_attributes()
        violations = _scan_file_for_piecewise_result_assertions(snippet, base_attrs, allowlist=frozenset())
        assert violations == []
