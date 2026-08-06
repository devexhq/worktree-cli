"""Unit tests for ``wt templates`` CLI commands."""

from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.templates.command import templates_list_command
from getworktree.core.templates.models import TemplateType

runner = CliRunner()


def test_cli_wt_templates_default() -> None:
    """Verify ``wt templates`` lists all built-in templates with table headers."""
    res = runner.invoke(app, ["templates"])

    assert res.exit_code == 0
    assert "wt-defined Templates:" in res.output
    assert "feature-dev" in res.output
    assert "run-tests" in res.output
    assert "git-checkpoint" in res.output
    assert "workflow" in res.output
    assert "task" in res.output
    assert "step" in res.output


def test_cli_wt_templates_type_filter_workflow() -> None:
    """Verify ``wt templates --type workflow`` outputs only workflow templates."""
    res = runner.invoke(app, ["templates", "--type", "workflow"])

    assert res.exit_code == 0
    assert "wt-defined Templates:" in res.output
    assert "feature-dev" in res.output
    assert "run-tests" not in res.output
    assert "git-checkpoint" not in res.output


def test_cli_wt_template_list_type_filter_task() -> None:
    """Verify ``wt template list --type task`` outputs only task templates."""
    res = runner.invoke(app, ["template", "list", "--type", "task"])

    assert res.exit_code == 0
    assert "wt-defined Templates:" in res.output
    assert "run-tests" in res.output
    assert "feature-dev" not in res.output


def test_cli_wt_template_list_type_filter_step() -> None:
    """Verify ``wt template list --type step`` outputs only step templates."""
    res = runner.invoke(app, ["template", "list", "--type", "step"])

    assert res.exit_code == 0
    assert "wt-defined Templates:" in res.output
    assert "git-checkpoint" in res.output
    assert "feature-dev" not in res.output


def test_cli_wt_templates_invalid_type() -> None:
    """Verify ``wt templates --type invalid`` returns validation error listing valid choices."""
    res = runner.invoke(app, ["templates", "--type", "invalid"])

    assert res.exit_code != 0
    assert "Invalid value for '--type'" in res.output or "invalid" in res.output
    assert "workflow" in res.output
    assert "task" in res.output
    assert "step" in res.output


def test_templates_list_command_direct_invocation() -> None:
    """Verify python command function ``templates_list_command``."""
    outcome = templates_list_command(type_filter=TemplateType.WORKFLOW)

    assert outcome.ok
    assert outcome.type_filter == TemplateType.WORKFLOW
    assert len(outcome.templates) > 0
    for tmpl in outcome.templates:
        assert tmpl.type == TemplateType.WORKFLOW
