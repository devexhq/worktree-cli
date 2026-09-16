"""Tier 4 architectural boundary and AST lint invariant tests."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Final

import pytest

from tests.lint.astlib import collect_python_files
from worktree.common.models import BaseResult

REPO_ROOT: Final[Path] = Path(__file__).parent.parent.parent
SRC_ROOT: Final[Path] = REPO_ROOT / "src" / "worktree"
TESTS_ROOT: Final[Path] = REPO_ROOT / "tests"

pytestmark = pytest.mark.invariant


def _check_fix_string(text: str, rel_path: Path, lineno: int) -> str | None:
    """Validate that a remediation fix string begins with a capital letter.

    Args:
        text: Remediation text string.
        rel_path: File path relative to repo root.
        lineno: Source code line number.

    Returns:
        Violation string if not capitalized, None otherwise.
    """
    trimmed = text.strip()
    if not trimmed:
        return f"{rel_path}:{lineno}: Remediation fix string is empty: {text!r}"

    stripped = trimmed.lstrip("\"'")
    if stripped.startswith("`"):
        return None

    if not stripped or not stripped[0].isupper():
        return f"{rel_path}:{lineno}: Remediation fix string does not begin with a capital letter: {text!r}"
    return None


def _extract_joined_str(expr: ast.JoinedStr) -> list[tuple[str, int]]:
    """Extract initial string literal prefix from an f-string."""
    if not expr.values:
        return []
    first_val = expr.values[0]
    if isinstance(first_val, ast.Constant) and isinstance(first_val.value, str):
        return [(first_val.value, expr.lineno)]
    return []


def _extract_strings_from_node(expr: ast.AST) -> list[tuple[str, int]]:
    """Extract candidate remediation strings and their line numbers from an AST node."""
    if isinstance(expr, (ast.List, ast.Tuple)):
        strings: list[tuple[str, int]] = []
        for elt in expr.elts:
            strings.extend(_extract_strings_from_node(elt))
        return strings

    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return [(expr.value, expr.lineno)]

    if isinstance(expr, ast.JoinedStr):
        return _extract_joined_str(expr)

    return []


def _validate_fix_expr(expr: ast.AST, rel_path: Path, violations: list[str]) -> None:
    """Validate all fix strings within an AST expression."""
    for text, lineno in _extract_strings_from_node(expr):
        violation = _check_fix_string(text, rel_path, lineno)
        if violation:
            violations.append(violation)


def _is_fixes_append_call(node: ast.Call) -> bool:
    """Check if Call node is fixes.append/extend(...) or obj.fixes.append/extend(...)."""
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in ("append", "extend"):
        return False
    target = node.func.value
    if isinstance(target, ast.Name) and target.id == "fixes":
        return bool(node.args)
    if isinstance(target, ast.Attribute) and target.attr == "fixes":
        return bool(node.args)
    return False


def _check_call_fixes(node: ast.Call, rel_path: Path, violations: list[str]) -> None:
    """Check an ast.Call node for uncapitalized fixes arguments or append/extend calls."""
    for kw in node.keywords:
        if kw.arg == "fixes":
            _validate_fix_expr(kw.value, rel_path, violations)

    if _is_fixes_append_call(node):
        _validate_fix_expr(node.args[0], rel_path, violations)


def _extract_target_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    """Extract variable names from an assignment node."""
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _is_remediation_variable(name: str) -> bool:
    """Check if variable name represents a remediation or fix container."""
    if "REMEDIATION" in name:
        return True
    if name.endswith("_FIXES") or name == "FIXES":
        return True
    return False


def _check_assign_fixes(node: ast.Assign | ast.AnnAssign, rel_path: Path, violations: list[str]) -> None:
    """Check assignment to remediation or fixes variables for uncapitalized strings."""
    if node.value is None:
        return
    target_names = _extract_target_names(node)
    if not any(_is_remediation_variable(name) for name in target_names):
        return

    if isinstance(node.value, ast.Dict):
        for val in node.value.values:
            _validate_fix_expr(val, rel_path, violations)
    elif isinstance(node.value, (ast.List, ast.Tuple)):
        _validate_fix_expr(node.value, rel_path, violations)


def _scan_file_for_fix_strings(file_path: Path) -> list[str]:
    """Scan a Python file for remediation fix strings and validate capitalization.

    Args:
        file_path: Path to the Python file.

    Returns:
        List of violation strings naming uncapitalized remediation fixes.
    """
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    rel_path = file_path.relative_to(REPO_ROOT)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _check_call_fixes(node, rel_path, violations)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            _check_assign_fixes(node, rel_path, violations)

    return violations


_CLI_RUNNER_RESULT_ATTRS: Final[set[str]] = {
    "exit_code",
    "stdout",
    "stderr",
    "output",
}


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
    return _extract_target_names(node)


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


def _scan_file_for_piecewise_result_assertions(file_path: Path, base_attrs: set[str]) -> list[str]:
    """Scan test file for individual field assertions on operation results."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    rel_path = file_path.relative_to(REPO_ROOT) if file_path.is_relative_to(REPO_ROOT) else file_path
    violations: list[str] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _scan_function_for_result_assertions(node, rel_path, base_attrs, violations)
        elif isinstance(node, ast.Assert):
            _check_assert_in_scope(node, rel_path, base_attrs, set(), violations)

    return violations


class ArchitectureBoundariesTests:
    """Tier 4 architectural boundary and AST lint invariant tests."""

    def test_all_emitted_remediation_fixes_are_capitalized(self) -> None:
        """Ensure all remediation suggestions and fixes begin with a capital letter."""
        files = collect_python_files(SRC_ROOT)
        violations: list[str] = []
        for file_path in files:
            violations.extend(_scan_file_for_fix_strings(file_path))

        assert not violations, "Found uncapitalized remediation fixes:\n" + "\n".join(violations)

    def test_tests_never_assert_individual_result_fields(self) -> None:
        """Ensure test files use whole-object comparison instead of piecewise result assertions."""
        all_files = collect_python_files(TESTS_ROOT)
        base_attrs = _get_base_result_attributes()
        violations: list[str] = []
        for file_path in all_files:
            if file_path.name == "test_architecture_boundaries.py":
                continue
            violations.extend(_scan_file_for_piecewise_result_assertions(file_path, base_attrs))

        assert not violations, "Found piecewise result assertions in tests:\n" + "\n".join(violations)

    def test_scanner_flags_piecewise_assertions(self, tmp_path: Path) -> None:
        """Ensure scanner flags prohibited piecewise assertions across naming variants."""
        snippet = tmp_path / "test_sample.py"
        snippet.write_text(
            "def test_func():\n"
            "    result1 = get_result()\n"
            "    assert result1.ok is True\n"
            "    result2 = get_result()\n"
            "    assert result2.errors == []\n"
            "    custom = StepResult()\n"
            "    assert custom.step_id == '1'\n"
            "    any_var = op()\n"
            "    assert any_var.status == 'ok'\n"
            "    res = runner.invoke()\n"
            "    assert res.exit_code == 0\n"
        )
        base_attrs = _get_base_result_attributes()
        violations = _scan_file_for_piecewise_result_assertions(snippet, base_attrs)
        assert len(violations) == 4
