"""Unit tests for catalog test-data helpers."""

from pathlib import Path

from tests.helpers import CatalogHelper, FileSystem


class CatalogHelperTests:
    """Unit tests for typed catalog fixture creation."""

    def test_blueprint_applies_defaults_and_explicit_overrides(self, tmp_path: Path) -> None:
        blueprint = CatalogHelper(FileSystem(tmp_path)).blueprint(
            key="lint",
            name="Run lint",
            steps=[{"id": "lint", "run": "ruff check ."}],
        )

        assert blueprint.instance.name == "Run lint"
        assert blueprint.instance.steps[0].id == "lint"
        assert blueprint.document["name"] == "Run lint"
        assert blueprint.catalog_item.key == "lint"

    def test_step_writes_file_definition_to_default_catalog_path(self, tmp_path: Path) -> None:
        step = CatalogHelper(FileSystem(tmp_path)).step(key="lint", run="ruff check .")

        path = step.create_file()

        assert path == tmp_path / ".worktree/catalog/steps/lint.yaml"
        assert "run: ruff check ." in path.read_text(encoding="utf-8")

    def test_document_returns_fresh_mutable_file_definition(self, tmp_path: Path) -> None:
        blueprint = CatalogHelper(FileSystem(tmp_path)).blueprint(key="lint")
        document = blueprint.model_dump("file_definition")
        document.pop("name")

        assert blueprint.document["name"] == "Sample Blueprint"

    def test_save_persists_helper_definition_through_catalog(self, tmp_path: Path) -> None:
        helper = CatalogHelper(FileSystem(tmp_path))
        blueprint = helper.blueprint(key="lint", name="Run lint")

        record = helper.save(blueprint)

        assert (record.key, record.name, record.path) == (
            "lint",
            "Run lint",
            Path("blueprints/lint.yml"),
        )
