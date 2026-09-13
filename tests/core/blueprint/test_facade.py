from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.assertions import assert_model_equal
from worktree.core.blueprint import Blueprint, BlueprintDefinition
from worktree.core.blueprint.models import BlueprintDefaults
from worktree.core.catalog import Catalog
from worktree.core.step.models import StepDefinition

pytestmark = pytest.mark.unit


class BlueprintDocumentNormalizationTests:
    """Unit tests verifying blueprint document default normalization contracts."""

    def test_blueprint_defaults_missing_name_from_file_stem(self, tmp_path: Path) -> None:
        """Blueprint loaded without explicit 'name' inherits catalog key / file stem."""
        blueprints_dir = tmp_path / ".worktree" / "catalog" / "blueprints"
        blueprints_dir.mkdir(parents=True, exist_ok=True)
        raw_yaml = "steps:\n  - id: ruff\n    run: ruff check .\n"
        (blueprints_dir / "lint-task.yml").write_text(raw_yaml, encoding="utf-8")

        blueprint = Blueprint.load("lint-task", catalog=Catalog(tmp_path))

        assert_model_equal(
            blueprint.definition,
            BlueprintDefinition(
                name="lint-task",
                description="",
                summary="",
                version=1,
                use_sandbox=True,
                timeout_seconds=None,
                env={},
                inputs={},
                defaults=BlueprintDefaults(),
                steps=[
                    StepDefinition(
                        id="ruff",
                        run="ruff check .",
                    )
                ],
            ),
        )

    def test_blueprint_normalizes_null_description_and_summary_to_empty(self) -> None:
        """Blueprint normalizes JSON/YAML null description and summary to empty strings."""
        definition = BlueprintDefinition.from_document(
            {"name": "ship", "description": None, "summary": None},
            key="ship",
        )
        blueprint = Blueprint(definition)

        assert_model_equal(
            blueprint.definition,
            BlueprintDefinition(
                name="ship",
                description="",
                summary="",
                version=1,
                use_sandbox=True,
                timeout_seconds=None,
                env={},
                inputs={},
                defaults=BlueprintDefaults(),
                steps=[],
            ),
        )
