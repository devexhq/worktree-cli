"""Blueprint domain facade."""

from __future__ import annotations

from typing import Any, ClassVar

from worktree.core.blueprint.models import BlueprintDefinition
from worktree.core.inputs import (
    InputResolveResult,
    Inputs,
    ParameterInput,
)
from worktree.core.step import LoopStepBlock, StepDefinition


class Blueprint:
    """Load, inspect, and dump a unified task/blueprint document."""

    spec: ClassVar[type[BlueprintDefinition]] = BlueprintDefinition

    def __init__(self, instance: BlueprintDefinition) -> None:
        self._instance = instance

    @property
    def definition(self) -> BlueprintDefinition:
        """Return the underlying wrapped BlueprintDefinition instance."""
        return self._instance

    @property
    def name(self) -> str:
        """Return the blueprint name."""
        return self._instance.name

    @property
    def key(self) -> str:
        """Return the blueprint key."""
        return self._instance.key

    @property
    def steps(self) -> list[StepDefinition | LoopStepBlock]:
        """Return the live steps list from the wrapped document."""
        return self._instance.steps

    @property
    def inputs(self) -> dict[str, ParameterInput]:
        """Return the live inputs mapping from the wrapped document."""
        return self._instance.inputs

    @property
    def use_sandbox(self) -> bool:
        """Return whether the document requests a git sandbox."""
        return self._instance.use_sandbox

    def dump(self) -> dict[str, Any]:
        """Return the in-memory document as a JSON-mode dict, including derived kind."""
        return self._instance.model_dump(mode="json")

    def resolve_inputs(
        self,
        cli_args: list[str] | None = None,
        *,
        overrides: dict[str, str | int | bool] | None = None,
    ) -> InputResolveResult:
        """Parse CLI args against this blueprint's declared inputs."""
        return Inputs.resolve(self.inputs, cli_args=cli_args, overrides=overrides)
