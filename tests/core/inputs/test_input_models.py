"""Unit tests for blueprint ParameterInput models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from worktree.core.inputs import InputResolveResult, InputType, ParameterInput


class InputModelTests:
    """Unit tests for ParameterInput and InputResolveResult data models."""

    def test_parameter_input_defaults(self) -> None:
        spec = ParameterInput()
        assert spec.type == InputType.STRING
        assert spec.required is False
        assert spec.default is None
        assert spec.aliases == []
        assert spec.description is None

    def test_parameter_input_coerces_type_and_aliases(self) -> None:
        spec = ParameterInput.model_validate(
            {
                "type": "boolean",
                "description": "Allow empty commit",
                "required": False,
                "default": False,
                "aliases": "--allow-empty",
            }
        )
        assert spec.type == InputType.BOOLEAN
        assert spec.default is False
        assert spec.aliases == ["--allow-empty"]

    def test_parameter_input_rejects_empty_alias(self) -> None:
        with pytest.raises(ValidationError):
            ParameterInput.model_validate({"aliases": ["", "  "]})

    def test_input_resolve_result_ok_property(self) -> None:
        ok = InputResolveResult(values={"message": "hi"})
        assert ok.ok is True

        missing = InputResolveResult(missing=["message"])
        assert missing.ok is False

        errored = InputResolveResult(errors=["bad syntax"])
        assert errored.ok is False

    def test_format_input_spec(self) -> None:
        from worktree.core.inputs import format_input_spec

        line = format_input_spec(
            "message",
            ParameterInput(
                type=InputType.STRING,
                required=True,
                aliases=["-m", "--message"],
                description="Commit message",
            ),
        )
        assert line.startswith("  - message (string, required")
        assert "aliases=['-m', '--message']" in line
        assert "Commit message" in line

        optional = format_input_spec(
            "allow_empty",
            ParameterInput(type=InputType.BOOLEAN, default=False, aliases=["--allow-empty"]),
        )
        assert "optional" in optional
        assert "default=False" in optional
