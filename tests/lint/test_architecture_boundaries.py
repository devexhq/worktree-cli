"""Tier 4 architectural boundary and AST lint invariant tests."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import Final

import pytest

from worktree.common.models import BaseResult

REPO_ROOT: Final[Path] = Path(__file__).parent.parent.parent
SRC_ROOT: Final[Path] = REPO_ROOT / "src" / "worktree"
CORE_ROOT: Final[Path] = SRC_ROOT / "core"
TESTS_ROOT: Final[Path] = REPO_ROOT / "tests"
CORE_TESTS_ROOT: Final[Path] = TESTS_ROOT / "core"
DISPATCHER_PATH: Final[Path] = SRC_ROOT / "cli" / "ui" / "dispatcher.py"

pytestmark = pytest.mark.invariant


def _collect_python_files(directory: Path) -> list[Path]:
    """Collect all python source files within a directory tree.

    Args:
        directory: Target root path to search.

    Returns:
        List of python file paths. Returns empty list if directory does not exist.
    """
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(p for p in directory.rglob("*.py") if p.is_file())


def _is_banned_import(name: str | None, banned_prefix: str) -> bool:
    """Check if import name matches banned prefix."""
    if not name:
        return False
    if name == banned_prefix:
        return True
    return name.startswith(f"{banned_prefix}.")


def _check_import_node(node: ast.Import, banned_prefix: str, rel_path: Path) -> list[str]:
    """Check an Import node for banned prefixes."""
    violations: list[str] = []
    for alias in node.names:
        if _is_banned_import(alias.name, banned_prefix):
            violations.append(f"{rel_path}:{node.lineno}: Layer violation: imports '{alias.name}'")
    return violations


def _check_import_from_node(node: ast.ImportFrom, banned_prefix: str, rel_path: Path) -> list[str]:
    """Check an ImportFrom node for banned prefixes."""
    if _is_banned_import(node.module, banned_prefix):
        return [f"{rel_path}:{node.lineno}: Layer violation: imports '{node.module}'"]
    return []


def _scan_file_for_banned_imports(file_path: Path, banned_prefix: str) -> list[str]:
    """Scan a Python file for banned import statements using AST analysis.

    Args:
        file_path: Path to the Python file.
        banned_prefix: Banned package prefix (e.g. 'worktree.cli').

    Returns:
        List of informative violation strings with file path and line number.
    """
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    rel_path = file_path.relative_to(REPO_ROOT)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            violations.extend(_check_import_node(node, banned_prefix, rel_path))
        elif isinstance(node, ast.ImportFrom):
            violations.extend(_check_import_from_node(node, banned_prefix, rel_path))

    return violations


def _is_banned_echo_attribute(func: ast.AST) -> bool:
    """Check if AST node is typer.echo, typer.secho, click.echo, or click.secho."""
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in ("echo", "secho"):
        return False
    if not isinstance(func.value, ast.Name):
        return False
    return func.value.id in ("typer", "click")


def _check_call_for_banned_output(node: ast.Call, rel_path: Path) -> str | None:
    """Inspect an ast.Call node for banned direct output functions.

    Args:
        node: AST Call node.
        rel_path: File path relative to repo root.

    Returns:
        Violation string if banned call detected, None otherwise.
    """
    if isinstance(node.func, ast.Name) and node.func.id == "print":
        return f"{rel_path}:{node.lineno}: Banned direct terminal output call 'print'"

    if _is_banned_echo_attribute(node.func):
        attr_node = node.func
        assert isinstance(attr_node, ast.Attribute)
        assert isinstance(attr_node.value, ast.Name)
        return f"{rel_path}:{node.lineno}: Banned direct terminal output call '{attr_node.value.id}.{attr_node.attr}'"

    return None


def _check_import_from_output(node: ast.ImportFrom, rel_path: Path) -> list[str]:
    """Check if ImportFrom node imports echo/secho from typer or click."""
    if node.module not in ("typer", "click"):
        return []
    violations: list[str] = []
    for alias in node.names:
        if alias.name in ("echo", "secho"):
            violations.append(
                f"{rel_path}:{node.lineno}: Banned direct terminal output import '{alias.name}' from '{node.module}'"
            )
    return violations


def _scan_file_for_terminal_output(file_path: Path) -> list[str]:
    """Scan a Python file for banned direct console output.

    Args:
        file_path: Path to the Python file.

    Returns:
        List of violation strings with file path and line number.
    """
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    rel_path = file_path.relative_to(REPO_ROOT)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            violations.extend(_check_import_from_output(node, rel_path))
        elif isinstance(node, ast.Call):
            violation = _check_call_for_banned_output(node, rel_path)
            if violation:
                violations.append(violation)

    return violations


def _has_result_class_def(tree: ast.AST) -> bool:
    """Check if AST tree contains candidate Result class definitions."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Result") and node.name != "BaseResult":
            return True
    return False


def _file_to_module_name(file_path: Path) -> str:
    """Convert a file path under src/ to a dotted python module name."""
    rel = file_path.relative_to(REPO_ROOT / "src")
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_candidate_result_class(cls: type, cls_name: str, module_name: str) -> bool:
    """Check if class is a Result model defined in target module."""
    if getattr(cls, "__module__", None) != module_name:
        return False
    if cls_name == "BaseResult":
        return False
    return cls_name.endswith("Result")


def _inspect_module_result_classes(file_path: Path) -> list[str]:
    """Inspect classes ending with Result in a module to ensure BaseResult inheritance.

    Args:
        file_path: Path to the Python file in src/worktree.

    Returns:
        List of violation strings naming offending classes.
    """
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    if not _has_result_class_def(tree):
        return []

    module_name = _file_to_module_name(file_path)
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:
        return [f"Could not import {module_name}: {exc}"]

    violations: list[str] = []
    for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
        if _is_candidate_result_class(cls, cls_name, module_name) and not issubclass(cls, BaseResult):
            violations.append(f"{module_name}.{cls_name} does not inherit from BaseResult")

    return violations


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

    def test_core_never_imports_worktree_cli(self) -> None:
        """Ensure src/worktree/core never imports from worktree.cli."""
        files = _collect_python_files(CORE_ROOT)
        violations: list[str] = []
        for file_path in files:
            violations.extend(_scan_file_for_banned_imports(file_path, "worktree.cli"))

        assert not violations, "Found prohibited worktree.cli imports in src/worktree/core:\n" + "\n".join(violations)

    def test_tests_core_never_imports_worktree_cli(self) -> None:
        """Ensure core tests never import from worktree.cli."""
        files = _collect_python_files(CORE_TESTS_ROOT)
        violations: list[str] = []
        for file_path in files:
            violations.extend(_scan_file_for_banned_imports(file_path, "worktree.cli"))

        assert not violations, "Found prohibited worktree.cli imports in tests/core:\n" + "\n".join(violations)

    def test_zero_direct_terminal_output_outside_dispatcher(self) -> None:
        """Ensure print(), typer.echo(), and click.echo() only exist inside dispatcher.py."""
        all_files = _collect_python_files(SRC_ROOT)
        files = [p for p in all_files if p.resolve() != DISPATCHER_PATH.resolve()]
        violations: list[str] = []
        for file_path in files:
            violations.extend(_scan_file_for_terminal_output(file_path))

        assert not violations, "Found direct terminal output calls outside dispatcher.py:\n" + "\n".join(violations)

    def test_all_result_dtos_inherit_from_base_result(self) -> None:
        """Ensure all *Result DTO classes across src/worktree inherit from BaseResult."""
        files = _collect_python_files(SRC_ROOT)
        violations: list[str] = []
        for file_path in files:
            violations.extend(_inspect_module_result_classes(file_path))

        assert not violations, "Found Result classes not inheriting from BaseResult:\n" + "\n".join(violations)

    def test_all_emitted_remediation_fixes_are_capitalized(self) -> None:
        """Ensure all remediation suggestions and fixes begin with a capital letter."""
        files = _collect_python_files(SRC_ROOT)
        violations: list[str] = []
        for file_path in files:
            violations.extend(_scan_file_for_fix_strings(file_path))

        assert not violations, "Found uncapitalized remediation fixes:\n" + "\n".join(violations)

    def test_tests_never_assert_individual_result_fields(self) -> None:
        """Ensure test files use whole-object comparison instead of piecewise result assertions."""
        all_files = _collect_python_files(TESTS_ROOT)
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
