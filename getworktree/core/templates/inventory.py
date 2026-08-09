"""Inventory helper for discovering and reading built-in templates."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from getworktree.common.fs import scan_yaml_directory
from getworktree.common.models import YamlFile
from getworktree.core.templates.models import (
    BuiltinTemplate,
    BuiltinTemplateResult,
    TemplateType,
)


def _load_builtin_template(
    yaml_file: YamlFile, template_type: TemplateType
) -> tuple[BuiltinTemplate | None, str | None]:
    """Read and parse a single template YAML file into a BuiltinTemplate model.

    Returns:
        (template, error). On success error is None. Soft validation skips return
        (None, None). Unexpected failures return (None, error message).
    """
    try:
        if not isinstance(yaml_file.parsed, dict):
            return None, None

        name = str(yaml_file.parsed.get("name", ""))
        description = str(yaml_file.parsed.get("description", ""))
        summary = str(yaml_file.parsed.get("summary", ""))

        if not name or not description:
            return None, None

        # If YAML explicitly defines type, use it if valid, otherwise fallback to directory type
        raw_type = yaml_file.parsed.get("type")
        resolved_type = template_type
        if raw_type and isinstance(raw_type, str):
            try:
                resolved_type = TemplateType(raw_type)
            except ValueError:
                pass

        return (
            BuiltinTemplate(
                name=name,
                type=resolved_type,
                description=description,
                summary=summary,
                content=str(yaml_file.content),
            ),
            None,
        )
    except Exception as exc:
        return None, f"Failed to load built-in template '{yaml_file.path}': {exc}"


def _locate_template_files(*, filter_enum: TemplateType | None = None) -> tuple[list[BuiltinTemplate], list[str]]:
    type_subdirs: list[tuple[str, TemplateType]] = [
        ("workflows", TemplateType.WORKFLOW),
        ("tasks", TemplateType.TASK),
        ("steps", TemplateType.STEP),
    ]

    templates: list[BuiltinTemplate] = []
    errors: list[str] = []

    root = importlib.resources.files("getworktree.core.templates")

    for subdir_name, t_type in type_subdirs:
        if filter_enum is not None and filter_enum != t_type:
            continue

        subdir = Path(str(root.joinpath(subdir_name)))
        yaml_files = scan_yaml_directory(subdir)

        for file in yaml_files:
            tmpl, error = _load_builtin_template(file, t_type)
            if error:
                errors.append(error)
            if tmpl is not None:
                templates.append(tmpl)
    return templates, errors


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
                return BuiltinTemplateResult(errors=[f"Invalid template type filter: '{type_filter}'"])

    # Sort templates by name, then by type
    try:
        templates, errors = _locate_template_files(filter_enum=filter_enum)
        templates.sort(key=lambda t: (t.name, t.type.value))
        return BuiltinTemplateResult(templates=templates, errors=errors)
    except Exception as exc:
        return BuiltinTemplateResult(errors=[f"Failed to access package templates resource: {exc}"])


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
    for tmpl in res.templates:
        if tmpl.name == name:
            return tmpl
    return None
