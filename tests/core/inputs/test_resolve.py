"""Unit tests for CLI input parsing and pre-execution resolution."""

from __future__ import annotations

from worktree.core.inputs import (
    InputResolveResult,
    InputType,
    ParameterInput,
)
from worktree.core.inputs.services.resolve import (
    format_input_error_message,
    format_missing_inputs_error,
    resolve_inputs,
)


def _commit_inputs() -> dict[str, ParameterInput]:
    return {
        "message": ParameterInput(
            type=InputType.STRING,
            required=True,
            aliases=["-m", "--message"],
        ),
        "allow_empty": ParameterInput(
            type=InputType.BOOLEAN,
            default=False,
            aliases=["--allow-empty"],
        ),
    }


class InputResolveTests:
    """Unit tests for parameter input resolution and validation."""

    def test_resolve_inputs_alias_and_defaults(self) -> None:
        result = resolve_inputs(_commit_inputs(), cli_args=["-m", "ship it"])
        assert result.ok
        assert result.values == {"message": "ship it", "allow_empty": False}

    def test_resolve_inputs_generic_override(self) -> None:
        result = resolve_inputs(
            _commit_inputs(),
            cli_args=["-i", "message=from-override", "--allow-empty"],
        )
        assert result.ok
        assert result.values["message"] == "from-override"
        assert result.values["allow_empty"] is True

    def test_resolve_inputs_missing_required(self) -> None:
        result = resolve_inputs(_commit_inputs(), cli_args=[])
        assert not result.ok
        assert result.missing == ["message"]

    def test_resolve_inputs_invalid_override_syntax(self) -> None:
        result = resolve_inputs(_commit_inputs(), cli_args=["-i", "not-a-pair"])
        assert not result.ok
        assert result.errors
        assert "Invalid input syntax" in result.errors[0]

    def test_resolve_inputs_type_coercion_errors(self) -> None:
        declarations = {
            "count": ParameterInput(type=InputType.INTEGER, required=True, aliases=["-n"]),
            "flag": ParameterInput(type=InputType.BOOLEAN, required=True, aliases=["--flag"]),
        }
        bad_int = resolve_inputs(declarations, cli_args=["-n", "abc"])
        assert not bad_int.ok
        assert "expects an integer" in bad_int.errors[0]

        bad_bool = resolve_inputs(declarations, cli_args=["-n", "1", "--flag", "maybe"])
        assert not bad_bool.ok
        assert "expects a boolean" in bad_bool.errors[0]

    def test_resolve_inputs_warns_on_unknown_tokens(self) -> None:
        result = resolve_inputs(
            _commit_inputs(),
            cli_args=["-m", "ok", "--unknown", "positional"],
        )
        assert result.ok
        assert any("unrecognized option" in warning.lower() for warning in result.warnings)
        assert any("unexpected argument" in warning.lower() for warning in result.warnings)

    def test_format_missing_inputs_error_includes_usage(self) -> None:
        message = format_missing_inputs_error(
            kind="task",
            name="commit",
            missing=["message"],
            declarations=_commit_inputs(),
        )
        assert "Missing required input 'message' for task 'commit'." in message
        assert "wt task run commit -m <value>" in message
        assert "wt task run commit -i message=<value>" in message

    def test_format_input_error_message(self) -> None:
        # Error branch
        err_result = InputResolveResult(errors=["Invalid value for option '--foo'."])
        assert (
            format_input_error_message(
                kind="workflow",
                name="demo",
                result=err_result,
                declarations=_commit_inputs(),
            )
            == "Invalid value for option '--foo'."
        )

        # Missing branch
        missing_result = InputResolveResult(missing=["message"])
        msg = format_input_error_message(
            kind="workflow",
            name="demo",
            result=missing_result,
            declarations=_commit_inputs(),
        )
        assert "Missing required input 'message' for workflow 'demo'." in msg
