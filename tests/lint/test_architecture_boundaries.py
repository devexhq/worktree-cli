"""Architectural boundary enforcement tests verifying import and output isolation."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "worktree"


def _iter_python_files(directory: Path) -> list[Path]:
    return [p for p in directory.rglob("*.py") if p.is_file()]


def test_no_rich_imports_outside_cli_ui() -> None:
    """Ensure rich and rich.* are never imported outside src/worktree/cli/ui/."""
    allowed_dirs = [
        SRC_ROOT / "cli" / "ui",
    ]
    allowed_files: list[Path] = []

    violations: list[str] = []
    for file_path in _iter_python_files(SRC_ROOT):
        if any(file_path.is_relative_to(d) for d in allowed_dirs) or file_path in allowed_files:
            continue

        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "rich" or alias.name.startswith("rich."):
                        violations.append(f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "rich" or node.module.startswith("rich."):
                    violations.append(f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} imports from '{node.module}'")

    assert not violations, "Found prohibited 'rich' imports outside the display layer:\n" + "\n".join(violations)


def test_formatters_only_imported_by_dispatcher_and_tests() -> None:
    """Ensure worktree.cli.ui.formatters is only imported by dispatcher, formatters, and tests."""
    allowed_files = [
        SRC_ROOT / "cli" / "ui" / "dispatcher.py",
    ]
    allowed_dirs = [
        SRC_ROOT / "cli" / "ui" / "formatters",
    ]

    violations: list[str] = []
    for file_path in _iter_python_files(SRC_ROOT):
        if file_path in allowed_files or any(file_path.is_relative_to(d) for d in allowed_dirs):
            continue

        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "formatters" in alias.name:
                        violations.append(f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if "formatters" in node.module:
                    violations.append(f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} imports from '{node.module}'")

    assert not violations, "Found unauthorized imports of 'formatters':\n" + "\n".join(violations)


def test_no_direct_output_outside_dispatcher() -> None:
    """Ensure print, echo, and stream write calls exist only inside dispatcher.py."""
    dispatcher_file = SRC_ROOT / "cli" / "ui" / "dispatcher.py"
    violations: list[str] = []

    for file_path in _iter_python_files(SRC_ROOT):
        if file_path == dispatcher_file:
            continue

        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # print(...) or pprint(...)
                if isinstance(func, ast.Name) and func.id in ("print", "pprint"):
                    violations.append(f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} calls '{func.id}()'")
                # typer.echo(...) / typer.secho(...) / click.echo(...)
                elif isinstance(func, ast.Attribute) and func.attr in ("echo", "secho"):
                    violations.append(f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} calls '{func.attr}()'")
                # sys.stdout.write(...) / sys.stderr.write(...)
                elif isinstance(func, ast.Attribute) and func.attr == "write":
                    if isinstance(func.value, ast.Attribute) and func.value.attr in ("stdout", "stderr"):
                        violations.append(
                            f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} calls 'sys.{func.value.attr}.write()'"
                        )

    assert not violations, "Found direct console output outside dispatcher.py:\n" + "\n".join(violations)


def test_one_formatter_class_per_module() -> None:
    """Ensure each module in formatters/ defines exactly one Formatter class."""
    formatters_dir = SRC_ROOT / "cli" / "ui" / "formatters"
    violations: list[str] = []

    for file_path in _iter_python_files(formatters_dir):
        if file_path.name in ("__init__.py", "common.py"):
            continue

        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        formatter_classes = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and (
                node.name.endswith("Formatter")
                or any(isinstance(b, ast.Name) and "Formatter" in b.id for b in node.bases)
            )
        ]

        if len(formatter_classes) != 1:
            violations.append(
                f"{file_path.relative_to(formatters_dir)} defines {len(formatter_classes)} formatter classes: "
                f"{formatter_classes} (expected exactly 1)"
            )

    assert not violations, "Found modules with != 1 Formatter class:\n" + "\n".join(violations)


def test_no_renderers_files_exist() -> None:
    """Ensure zero files named renderers.py exist in the entire codebase."""
    found: list[str] = []
    for file_path in _iter_python_files(SRC_ROOT):
        if file_path.name == "renderers.py" or file_path.name.endswith("_renderers.py"):
            found.append(str(file_path.relative_to(SRC_ROOT)))

    assert not found, "Found obsolete renderers files that must be eliminated:\n" + "\n".join(found)


def test_core_and_common_have_zero_ui_dependencies() -> None:
    """Ensure core/ and common/ have zero imports of UI libraries or cli package."""
    forbidden_roots = {"rich", "typer", "click"}
    violations: list[str] = []

    for sub_dir in (SRC_ROOT / "core", SRC_ROOT / "common"):
        for file_path in _iter_python_files(sub_dir):
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_pkg = alias.name.split(".")[0]
                        if root_pkg in forbidden_roots or alias.name.startswith("worktree.cli"):
                            violations.append(f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} imports '{alias.name}'")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg in forbidden_roots or node.module.startswith("worktree.cli"):
                        violations.append(
                            f"{file_path.relative_to(SRC_ROOT)}:{node.lineno} imports from '{node.module}'"
                        )

    assert not violations, "Found UI dependencies inside core/ or common/:\n" + "\n".join(violations)
