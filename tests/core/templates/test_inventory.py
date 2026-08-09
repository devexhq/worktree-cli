"""Unit tests for built-in templates inventory parsing and filtering."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from getworktree.common.models import YamlFile
from getworktree.core.templates import inventory as inventory_mod
from getworktree.core.templates.inventory import (
    _load_builtin_template,
    list_builtin_templates,
)
from getworktree.core.templates.models import TemplateType


def test_list_builtin_templates_all() -> None:
    """Verify that all built-in templates are discovered across workflows, tasks, and steps."""
    result = list_builtin_templates()

    assert result.ok
    assert len(result.errors) == 0
    names = {t.name for t in result.templates}
    assert "feature-dev" in names
    assert "run-tests" in names
    assert "git-checkpoint" in names


def test_load_builtin_template_surfaces_exception() -> None:
    """Unexpected load failures return (None, error) instead of swallowing silently."""
    yaml_file = MagicMock(spec=YamlFile)
    yaml_file.path = Path("tasks/broken.yml")
    type(yaml_file).parsed = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

    tmpl, error = _load_builtin_template(yaml_file, TemplateType.TASK)

    assert tmpl is None
    assert error is not None
    assert "Failed to load built-in template" in error
    assert "tasks/broken.yml" in error
    assert "boom" in error


def test_list_builtin_templates_collects_per_file_load_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-file load errors land in BuiltinTemplateResult.errors; other templates still load."""
    original = inventory_mod._load_builtin_template
    calls = {"n": 0}

    def flaky_load(yaml_file: YamlFile, template_type: TemplateType):
        calls["n"] += 1
        if calls["n"] == 1:
            return None, f"Failed to load built-in template '{yaml_file.path}': boom"
        return original(yaml_file, template_type)

    monkeypatch.setattr(inventory_mod, "_load_builtin_template", flaky_load)

    result = inventory_mod.list_builtin_templates()

    assert any("Failed to load built-in template" in err and "boom" in err for err in result.errors)
    assert len(result.templates) >= 1


def test_list_builtin_templates_filtered_by_workflow() -> None:
    """Verify filtering by WORKFLOW type returns only workflow templates."""
    result = list_builtin_templates(type_filter=TemplateType.WORKFLOW)

    assert result.ok
    for tmpl in result.templates:
        assert tmpl.type == TemplateType.WORKFLOW
    names = [t.name for t in result.templates]
    assert "feature-dev" in names
    assert "run-tests" not in names


def test_list_builtin_templates_filtered_by_task() -> None:
    """Verify filtering by TASK type returns only task templates."""
    result = list_builtin_templates(type_filter="task")

    assert result.ok
    for tmpl in result.templates:
        assert tmpl.type == TemplateType.TASK
    names = [t.name for t in result.templates]
    assert "run-tests" in names
    assert "feature-dev" not in names


def test_list_builtin_templates_filtered_by_step() -> None:
    """Verify filtering by STEP type returns only step templates."""
    result = list_builtin_templates(type_filter="step")

    assert result.ok
    for tmpl in result.templates:
        assert tmpl.type == TemplateType.STEP
    names = [t.name for t in result.templates]
    assert "git-checkpoint" in names
    assert "feature-dev" not in names


def test_list_builtin_templates_invalid_filter() -> None:
    """Verify invalid type filter string returns error result."""
    result = list_builtin_templates(type_filter="invalid_type")

    assert not result.ok
    assert len(result.errors) == 1
    assert "Invalid template type filter" in result.errors[0]


def test_get_builtin_template_success() -> None:
    """Verify fetching a specific built-in template returns its metadata and YAML content."""
    from getworktree.core.templates.inventory import get_builtin_template

    tmpl = get_builtin_template("feature-dev")
    assert tmpl is not None
    assert tmpl.name == "feature-dev"
    assert tmpl.type == TemplateType.WORKFLOW
    assert "feature-dev" in tmpl.content
    assert "Standard feature development workflow" in tmpl.description


def test_get_builtin_template_not_found() -> None:
    """Verify fetching a non-existent template returns None."""
    from getworktree.core.templates.inventory import get_builtin_template

    assert get_builtin_template("non_existent_tmpl") is None
    assert get_builtin_template("feature-dev", type_filter=TemplateType.TASK) is None
