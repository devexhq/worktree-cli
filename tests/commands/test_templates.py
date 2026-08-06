"""Unit tests for ``wt templates`` CLI commands."""

from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.templates.command import templates_list_command
from getworktree.core.templates.models import TemplateType

runner = CliRunner()


def test_cli_wt_template_default() -> None:
    """Verify ``wt template`` lists all built-in templates with table headers."""
    res = runner.invoke(app, ["template"])

    assert res.exit_code == 0
    assert "wt-defined Templates:" in res.output
    assert "feature-dev" in res.output
    assert "run-tests" in res.output
    assert "git-checkpoint" in res.output
    assert "workflow" in res.output
    assert "task" in res.output
    assert "step" in res.output


def test_cli_wt_template_type_filter_workflow() -> None:
    """Verify ``wt template --type workflow`` outputs only workflow templates."""
    res = runner.invoke(app, ["template", "--type", "workflow"])

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


def test_cli_wt_template_invalid_type() -> None:
    """Verify ``wt template --type invalid`` returns validation error listing valid choices."""
    res = runner.invoke(app, ["template", "--type", "invalid"])

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


def test_cli_wt_template_show_success() -> None:
    """Verify ``wt template show feature-dev`` displays template metadata and content."""
    res = runner.invoke(app, ["template", "show", "feature-dev"])

    assert res.exit_code == 0
    assert "Template:" in res.output
    assert "feature-dev" in res.output
    assert "Standard feature development workflow" in res.output
    assert "Definition:" in res.output


def test_cli_wt_template_show_task_with_type() -> None:
    """Verify ``wt template show run-tests --type task`` displays task template detail."""
    res = runner.invoke(app, ["template", "show", "run-tests", "--type", "task"])

    assert res.exit_code == 0
    assert "Template:" in res.output
    assert "run-tests" in res.output
    assert "Execute pytest suite with coverage" in res.output


def test_cli_wt_template_show_not_found() -> None:
    """Verify ``wt template show non-existent`` returns exit code 1 and error panel."""
    res = runner.invoke(app, ["template", "show", "non-existent"])

    assert res.exit_code == 1
    assert "Template 'non-existent' not found" in res.output


def test_template_show_command_direct_invocation() -> None:
    """Verify python command function ``template_show_command``."""
    from getworktree.commands.templates.command import template_show_command

    outcome = template_show_command("feature-dev")

    assert outcome.ok
    assert outcome.template is not None
    assert outcome.template.name == "feature-dev"
    assert outcome.template.type == TemplateType.WORKFLOW
