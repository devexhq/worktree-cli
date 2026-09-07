"""Tier 4 architectural invariants for UI component formatters and view models."""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
from enum import Enum
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel

import worktree.cli.ui.formatters as formatters_pkg
from worktree.cli.ui.dispatcher import ui_dispatcher
from worktree.cli.ui.formatters import FORMATTER_REGISTRY
from worktree.common.types import ComponentFormatter

SRC_ROOT: Final[Path] = Path(__file__).parent.parent.parent / "src" / "worktree"
FORMATTERS_DIR: Final[Path] = SRC_ROOT / "cli" / "ui" / "formatters"
RICH_MARKUP_PATTERN: Final[re.Pattern[str]] = re.compile(r"\[/?[a-z ]+\]")


def _iter_view_modules(directory: Path = FORMATTERS_DIR) -> list[Path]:
    """Discover all *_view.py and *_views.py files under formatters directory."""
    return sorted(p for p in directory.rglob("*.py") if p.is_file() and p.name.endswith(("_view.py", "_views.py")))


def _is_docstring(node: ast.AST, parent_map: dict[ast.AST, ast.AST]) -> bool:
    """Check if an AST string constant node is a docstring."""
    parent = parent_map.get(node)
    if not isinstance(parent, ast.Expr):
        return False
    grandparent = parent_map.get(parent)
    if grandparent is None:
        return False
    body = getattr(grandparent, "body", None)
    if isinstance(body, list) and body and body[0] is parent:
        return isinstance(grandparent, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    return False


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Build a mapping from child AST nodes to their direct parent nodes."""
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    return parent_map


def _check_constant_node(node: ast.AST, parent_map: dict[ast.AST, ast.AST], file_name: str) -> str | None:
    """Return violation string if constant node is a non-docstring string with markup."""
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return None
    if _is_docstring(node, parent_map):
        return None
    if RICH_MARKUP_PATTERN.search(node.value):
        lineno = getattr(node, "lineno", "?")
        return f"{file_name}:{lineno} literal contains Rich markup: {node.value!r}"
    return None


def _find_ast_markup_violations(tree: ast.AST, file_path: Path) -> list[str]:
    """Inspect AST string constants (excluding docstrings) for Rich markup."""
    parent_map = _build_parent_map(tree)
    violations: list[str] = []
    for node in ast.walk(tree):
        violation = _check_constant_node(node, parent_map, file_path.name)
        if violation is not None:
            violations.append(violation)
    return violations


def _module_name_from_path(file_path: Path) -> str:
    """Convert source file path to python module import string."""
    rel = file_path.relative_to(SRC_ROOT.parent)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def _check_value_for_rich_markup(value: object, location: str) -> list[str]:
    """Check an object recursively if string, list, or dict for Rich markup."""
    violations: list[str] = []
    if isinstance(value, str):
        if RICH_MARKUP_PATTERN.search(value):
            violations.append(f"{location} contains Rich markup: {value!r}")
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            violations.extend(_check_value_for_rich_markup(item, location))
    elif isinstance(value, dict):
        for k, v in value.items():
            violations.extend(_check_value_for_rich_markup(v, f"{location}[{k!r}]"))
    return violations


def _check_model_fields(cls: type[BaseModel], module_name: str) -> list[str]:
    """Check default values of a BaseModel class for Rich markup."""
    violations: list[str] = []
    for field_name, field_info in cls.model_fields.items():
        if field_info.default is not None:
            loc = f"{module_name}.{cls.__name__}.{field_name} default"
            violations.extend(_check_value_for_rich_markup(field_info.default, loc))
    return violations


def _check_enum_members(cls: type[Enum], module_name: str) -> list[str]:
    """Check member values of an Enum class for Rich markup."""
    violations: list[str] = []
    for member in cls:
        loc = f"{module_name}.{cls.__name__}.{member.name} value"
        violations.extend(_check_value_for_rich_markup(member.value, loc))
    return violations


def _find_class_markup_violations(obj: type[object], module_name: str) -> list[str]:
    """Check a single class if it is a BaseModel or Enum defined in the target module."""
    if obj.__module__ != module_name:
        return []
    if issubclass(obj, BaseModel):
        return _check_model_fields(obj, module_name)
    if issubclass(obj, Enum):
        return _check_enum_members(obj, module_name)
    return []


def _find_model_markup_violations(module_name: str) -> list[str]:
    """Introspect all BaseModel and Enum classes in module for Rich markup in defaults."""
    mod = importlib.import_module(module_name)
    violations: list[str] = []
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        violations.extend(_find_class_markup_violations(obj, module_name))
    return violations


def test_view_models_contain_no_rich_markup() -> None:
    """Ensure no view model definition or default contains Rich markup tags."""
    view_files = _iter_view_modules()
    assert len(view_files) >= 7, f"Expected at least 7 view modules, found {len(view_files)}"

    all_violations: list[str] = []
    for file_path in view_files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        all_violations.extend(_find_ast_markup_violations(tree, file_path))

        mod_name = _module_name_from_path(file_path)
        all_violations.extend(_find_model_markup_violations(mod_name))

    assert not all_violations, "Found Rich markup in view models:\n" + "\n".join(all_violations)


def _import_all_formatter_modules() -> None:
    """Import all submodules under worktree.cli.ui.formatters to ensure subclasses are defined."""
    for module_info in pkgutil.walk_packages(formatters_pkg.__path__, prefix="worktree.cli.ui.formatters."):
        importlib.import_module(module_info.name)


def _get_all_formatter_subclasses() -> list[type[ComponentFormatter[Any, Any]]]:
    """Return all concrete ComponentFormatter subclasses defined under worktree.cli.ui.formatters."""
    _import_all_formatter_modules()
    classes: set[type[ComponentFormatter[Any, Any]]] = set()
    to_visit: list[type[ComponentFormatter[Any, Any]]] = list(ComponentFormatter.__subclasses__())

    while to_visit:
        cls = to_visit.pop()
        to_visit.extend(cls.__subclasses__())
        if inspect.isabstract(cls):
            continue
        if cls.__module__.startswith("worktree.cli.ui.formatters"):
            classes.add(cls)

    return sorted(classes, key=lambda c: f"{c.__module__}.{c.__name__}")


def test_no_formatter_subclass_overrides_to_json_serializable() -> None:
    """Ensure no ComponentFormatter subclass overrides to_json_serializable in its class dict."""
    subclasses = _get_all_formatter_subclasses()
    assert len(subclasses) >= 33, f"Expected at least 33 formatter subclasses, found {len(subclasses)}"

    violations: list[str] = []
    for cls in subclasses:
        if "to_json_serializable" in cls.__dict__:
            violations.append(f"{cls.__name__} in {cls.__module__} overrides to_json_serializable")

    assert not violations, "Found formatters overriding to_json_serializable:\n" + "\n".join(violations)


def _calls_self_transform(fn_node: ast.FunctionDef) -> bool:
    """Return True if FunctionDef contains a call to self.transform(...)."""
    for node in ast.walk(fn_node):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr == "transform"
        ):
            return True
    return False


def _find_data_attribute_accesses(fn_node: ast.FunctionDef, param_name: str) -> list[str]:
    """Find direct attribute accesses on the domain data parameter within to_rich."""
    violations: list[str] = []
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == param_name:
            violations.append(f"line {node.lineno}: direct access '{param_name}.{node.attr}'")
    return violations


def _find_class_node(tree: ast.AST, class_name: str) -> ast.ClassDef | None:
    """Find a top-level or nested ClassDef node matching class_name."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _find_to_rich_function(cls_node: ast.ClassDef) -> ast.FunctionDef | None:
    """Locate the to_rich FunctionDef within a ClassDef body."""
    for node in cls_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == "to_rich":
            return node
    return None


def _check_to_rich_data_usage(to_rich_fn: ast.FunctionDef, class_name: str) -> list[str]:
    """Verify to_rich calls self.transform and does not directly access data attributes."""
    violations: list[str] = []
    if not _calls_self_transform(to_rich_fn):
        violations.append(f"{class_name}.to_rich does not call self.transform(...)")

    if len(to_rich_fn.args.args) >= 2:
        data_param = to_rich_fn.args.args[1].arg
        direct_accesses = _find_data_attribute_accesses(to_rich_fn, data_param)
        for access in direct_accesses:
            violations.append(f"{class_name}.to_rich {access}")
    return violations


def _check_formatter_to_rich(cls: type[object]) -> list[str]:
    """Verify a single formatter class obeys the derivation separation contract in to_rich."""
    src_file = Path(inspect.getfile(cls))
    tree = ast.parse(src_file.read_text(encoding="utf-8"), filename=str(src_file))
    cls_node = _find_class_node(tree, cls.__name__)
    if cls_node is None:
        return [f"Could not find ClassDef for {cls.__name__} in {src_file}"]

    to_rich_fn = _find_to_rich_function(cls_node)
    if to_rich_fn is None:
        return [f"{cls.__name__} does not define to_rich()"]

    return _check_to_rich_data_usage(to_rich_fn, cls.__name__)


def test_to_rich_does_not_derive_from_domain_model() -> None:
    """Ensure to_rich calls transform() and does not access domain data attributes directly."""
    subclasses = _get_all_formatter_subclasses()
    transform_formatters = [cls for cls in subclasses if "transform" in cls.__dict__]
    assert len(transform_formatters) >= 12, (
        f"Expected at least 12 formatters with transform(), found {len(transform_formatters)}"
    )

    violations: list[str] = []
    for cls in transform_formatters:
        violations.extend(_check_formatter_to_rich(cls))

    assert not violations, "Found violations of derivation separation in to_rich:\n" + "\n".join(violations)


def test_formatter_registry_structure() -> None:
    """Ensure FORMATTER_REGISTRY contains valid model and formatter mappings."""
    assert len(FORMATTER_REGISTRY) == 33
    for model_cls, formatter_cls in FORMATTER_REGISTRY.items():
        assert issubclass(model_cls, BaseModel)
        assert issubclass(formatter_cls, ComponentFormatter)


def test_ui_dispatcher_registers_all_registry_formatters() -> None:
    """Ensure default ui_dispatcher wires every mapping in FORMATTER_REGISTRY."""
    assert len(ui_dispatcher._registry) == len(FORMATTER_REGISTRY)
    for model_cls, formatter_cls in FORMATTER_REGISTRY.items():
        assert model_cls in ui_dispatcher._registry
        assert type(ui_dispatcher._registry[model_cls]) is formatter_cls
