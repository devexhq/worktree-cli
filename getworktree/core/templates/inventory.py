"""Inventory helper for discovering and reading built-in templates."""

from __future__ import annotations

import importlib.resources
from typing import Any

import yaml

from getworktree.core.templates.models import (
    BuiltinTemplate,
    BuiltinTemplateResult,
    TemplateType,
)


def _load_builtin_template(
    file_path: Any, template_type: TemplateType
) -> BuiltinTemplate | None:
    """Read and parse a single template YAML file into a BuiltinTemplate model."""
    try:
        content = file_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            return None

        name = str(parsed.get("name", ""))
        description = str(parsed.get("description", ""))
        summary = str(parsed.get("summary", ""))

        if not name or not description:
            return None

        # If YAML explicitly defines type, use it if valid, otherwise fallback to directory type
        raw_type = parsed.get("type")
        resolved_type = template_type
        if raw_type and isinstance(raw_type, str):
            try:
                resolved_type = TemplateType(raw_type)
            except ValueError:
                pass

        return BuiltinTemplate(
            name=name,
            type=resolved_type,
            description=description,
            summary=summary,
            content=content,
        )
    except Exception:
        return None


def list_builtin_templates(
    type_filter: TemplateType | str | None = None,
) -> BuiltinTemplateResult:
    """Discover and parse built-in template definitions shipped with Worktree.

    Args:
        type_filter: Optional filter to restrict templates by type (workflow, task, step).

    Returns:
        BuiltinTemplateResult containing valid BuiltinTemplate items.
    """
    filter_enum: TemplateType | None = None
    if type_filter is not None:
        if isinstance(type_filter, TemplateType):
            filter_enum = type_filter
        else:
            try:
                filter_enum = TemplateType(str(type_filter).lower())
            except ValueError:
                return BuiltinTemplateResult(
                    errors=[f"Invalid template type filter: '{type_filter}'"]
                )

    type_subdirs: list[tuple[str, TemplateType]] = [
        ("workflows", TemplateType.WORKFLOW),
        ("tasks", TemplateType.TASK),
        ("steps", TemplateType.STEP),
    ]

    templates: list[BuiltinTemplate] = []

    try:
        root = importlib.resources.files("getworktree.core.templates")
    except Exception as exc:
        return BuiltinTemplateResult(
            errors=[f"Failed to access package templates resource: {exc}"]
        )

    for subdir_name, t_type in type_subdirs:
        if filter_enum is not None and filter_enum != t_type:
            continue

        subdir = root.joinpath(subdir_name)
        if not subdir.is_dir():
            continue

        for item in subdir.iterdir():
            if item.name.endswith(".yml") or item.name.endswith(".yaml"):
                if item.name.startswith("__init__"):
                    continue
                tmpl = _load_builtin_template(item, t_type)
                if tmpl is not None:
                    templates.append(tmpl)

    # Sort templates by name, then by type
    templates.sort(key=lambda t: (t.name, t.type.value))

    return BuiltinTemplateResult(templates=templates)


def get_builtin_template(
    name: str,
    type_filter: TemplateType | str | None = None,
) -> BuiltinTemplate | None:
    """Find and return a single built-in template by name and optional type.

    Args:
        name: Template name (e.g. 'feature-dev').
        type_filter: Optional template type filter.

    Returns:
        Matching BuiltinTemplate or None if not found.
    """
    res = list_builtin_templates(type_filter=type_filter)
    if not res.ok:
        return None
    for tmpl in res.templates:
        if tmpl.name == name:
            return tmpl
    return None
