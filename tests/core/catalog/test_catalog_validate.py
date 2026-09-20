"""Tier 1 domain contract tests for Catalog.validate (wt catalog validate)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
import yaml

from tests.harness.catalog import write_runnable_blueprint
from tests.harness.matchers import assert_model_equal
from worktree.core.blueprint.models import BlueprintDefinition
from worktree.core.catalog import Catalog
from worktree.core.catalog.models import CatalogValidateResult, CatalogValidateStatus
from worktree.core.db import CatalogItemType
from worktree.core.step.models import StepDefinition


def _validate(target: str, *, path: Path, item_type: CatalogItemType | None = None) -> CatalogValidateResult:
    """Call Catalog.validate with the real BlueprintDefinition/StepDefinition schema classes."""
    return Catalog(path=path).validate(
        target,
        item_type=item_type,
        blueprint_cls=BlueprintDefinition,
        step_cls=StepDefinition,
    )


def _write_yaml(path: Path, payload: dict[str, object]) -> Path:
    """Write payload as YAML to path, preserving key order, and return path."""
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


class CatalogValidateServiceTests:
    """Tier 1 domain contract tests for Catalog.validate."""

    def test_validate_direct_file_path_resolves_and_validates(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: absolute file path target with item_type=BLUEPRINT validates directly; status OK, resolved_path set."""
        target_path = _write_yaml(
            isolated_workspace / "external.yml",
            {"name": "external", "steps": [{"id": "s1", "run": "echo hi"}]},
        )

        result = _validate(str(target_path), path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.OK,
                valid=True,
                target=str(target_path),
                resolved_path=target_path,
                item_type="blueprint",
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_validate_catalog_name_resolves_via_get(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: indexed catalog name resolves via Catalog.get; item_type='blueprint' taken from the record."""
        write_runnable_blueprint(isolated_workspace, key="sample-flow", steps=[{"id": "s1", "run": "echo hi"}])

        result = _validate("sample-flow", path=isolated_workspace)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.OK,
                valid=True,
                target="sample-flow",
                resolved_path=isolated_workspace / ".worktree" / "catalog" / "blueprints" / "sample-flow.yml",
                item_type="blueprint",
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_validate_unknown_name_returns_not_found(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: unmatched name returns status=NOT_FOUND with CATALOG_ITEM_NOT_FOUND error."""
        result = _validate("nonexistent-flow", path=isolated_workspace)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.NOT_FOUND,
                valid=False,
                target="nonexistent-flow",
                resolved_path=None,
                item_type=None,
                errors=["Catalog item 'nonexistent-flow' not found (CATALOG_ITEM_NOT_FOUND)."],
                warnings=[],
                fixes=["Check that 'nonexistent-flow' names an indexed catalog item, or pass a file path instead."],
            ),
        )

    def test_validate_file_target_without_type_returns_type_required(
        self, isolated_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[tier-1/domain] Catalog.validate: file target with item_type=None returns status=TYPE_REQUIRED with CATALOG_TYPE_REQUIRED, never reading the file."""
        draft_path = _write_yaml(isolated_workspace / "draft.yml", {"name": "draft"})

        def _fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
            raise AssertionError("draft.yml contents must not be read before --type is validated")

        monkeypatch.setattr(Path, "read_text", _fail_read_text)

        result = _validate("draft.yml", path=isolated_workspace, item_type=None)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.TYPE_REQUIRED,
                valid=False,
                target="draft.yml",
                resolved_path=draft_path,
                item_type=None,
                errors=["'--type' is required to validate file target 'draft.yml' (CATALOG_TYPE_REQUIRED)."],
                warnings=[],
                fixes=["Pass --type blueprint or --type step for a file target."],
            ),
        )

    def test_validate_unreadable_file_returns_unreadable_status(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: unreadable file path (item_type=BLUEPRINT) returns status=UNREADABLE with CATALOG_FILE_UNREADABLE."""
        target_path = _write_yaml(isolated_workspace / "noperm.yml", {"name": "noperm"})
        target_path.chmod(0)
        try:
            if os.access(target_path, os.R_OK):
                pytest.skip("filesystem still allows reading unreadable mode")

            result = _validate("noperm.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)
        finally:
            target_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.UNREADABLE,
                valid=False,
                target="noperm.yml",
                resolved_path=target_path,
                item_type="blueprint",
                errors=[
                    f"Failed to read '{target_path}': [Errno 13] Permission denied: '{target_path}' "
                    "(CATALOG_FILE_UNREADABLE)."
                ],
                warnings=[],
                fixes=[f"Check that '{target_path}' exists and is readable."],
            ),
        )

    def test_validate_yaml_syntax_error_reports_line_and_column(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: YAML scanner error (item_type=BLUEPRINT) returns status=SYNTAX_ERROR with line/column in the error text."""
        target_path = isolated_workspace / "bad.yml"
        target_path.write_text("foo: bar: baz\n", encoding="utf-8")

        result = _validate("bad.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert result.status == CatalogValidateStatus.SYNTAX_ERROR
        assert result.valid is False
        assert len(result.errors) == 1
        assert "CATALOG_YAML_SYNTAX_ERROR" in result.errors[0]
        assert "line 1, column 9" in result.errors[0]

    def test_validate_non_mapping_root_returns_invalid(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: list-rooted YAML (item_type=BLUEPRINT) returns status=INVALID with CATALOG_ROOT_NOT_OBJECT."""
        target_path = isolated_workspace / "list.yml"
        target_path.write_text("- a\n- b\n", encoding="utf-8")

        result = _validate("list.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.INVALID,
                valid=False,
                target="list.yml",
                resolved_path=target_path,
                item_type="blueprint",
                errors=[f"'{target_path}' root content must be a YAML mapping (CATALOG_ROOT_NOT_OBJECT)."],
                warnings=[],
                fixes=[f"Rewrite '{target_path}' with a top-level YAML mapping (key: value pairs)."],
            ),
        )

    def test_validate_schema_invalid_blueprint_reports_field_paths(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: invalid timeout_seconds type reports 'timeout_seconds' field path and CATALOG_SCHEMA_INVALID."""
        _write_yaml(
            isolated_workspace / "bad_timeout.yml",
            {"name": "bad-timeout", "timeout_seconds": "not-a-number", "steps": [{"id": "s1", "run": "echo hi"}]},
        )

        result = _validate("bad_timeout.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert result.status == CatalogValidateStatus.INVALID
        assert result.valid is False
        assert len(result.errors) == 1
        assert "timeout_seconds" in result.errors[0]
        assert "CATALOG_SCHEMA_INVALID" in result.errors[0]

    def test_validate_step_shape_conflict_surfaces_as_schema_error(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: run+uses conflict on a step (item_type=STEP) surfaces as a schema error, not a separate semantic check."""
        _write_yaml(
            isolated_workspace / "conflict.yml",
            {"id": "s1", "run": "pytest", "uses": "wt/ai-code-patcher"},
        )

        result = _validate("conflict.yml", path=isolated_workspace, item_type=CatalogItemType.STEP)

        assert result.status == CatalogValidateStatus.INVALID
        assert result.valid is False
        assert len(result.errors) == 1
        assert "run" in result.errors[0]
        assert "uses" in result.errors[0]
        assert "CATALOG_SCHEMA_INVALID" in result.errors[0]

    def test_validate_step_target_uses_step_schema(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: file target with item_type=STEP missing required id fails StepDefinition schema validation."""
        _write_yaml(isolated_workspace / "missing_id.yml", {"run": "pytest"})

        result = _validate("missing_id.yml", path=isolated_workspace, item_type=CatalogItemType.STEP)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.INVALID,
                valid=False,
                target="missing_id.yml",
                resolved_path=isolated_workspace / "missing_id.yml",
                item_type="step",
                errors=["id: Field required (CATALOG_SCHEMA_INVALID)."],
                warnings=[],
                fixes=["Fix the reported schema error for target 'missing_id'."],
            ),
        )

    def test_validate_duplicate_step_id_reports_error(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: two top-level steps sharing id='run-tests' reports CATALOG_DUPLICATE_STEP_ID."""
        _write_yaml(
            isolated_workspace / "dup.yml",
            {"name": "d", "steps": [{"id": "run-tests", "run": "pytest"}, {"id": "run-tests", "run": "pytest -x"}]},
        )

        result = _validate("dup.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.INVALID,
                valid=False,
                target="dup.yml",
                resolved_path=isolated_workspace / "dup.yml",
                item_type="blueprint",
                errors=["Step id 'run-tests' is used by more than one step (CATALOG_DUPLICATE_STEP_ID)."],
                warnings=[],
                fixes=["Resolve: Step id 'run-tests' is used by more than one step (CATALOG_DUPLICATE_STEP_ID)."],
            ),
        )

    def test_validate_duplicate_step_id_in_nested_loop_reports_error(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: duplicate ids inside a loop's 'do' block report CATALOG_DUPLICATE_STEP_ID."""
        _write_yaml(
            isolated_workspace / "loopdup.yml",
            {
                "name": "loop-dup",
                "steps": [
                    {
                        "id": "loop-1",
                        "type": "loop",
                        "until": ["steps.inner.exit_code == 0"],
                        "do": [
                            {"id": "inner", "run": "echo 1"},
                            {"id": "inner", "run": "echo 2"},
                        ],
                    }
                ],
            },
        )

        result = _validate("loopdup.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert result.status == CatalogValidateStatus.INVALID
        assert result.valid is False
        assert result.errors == ["Step id 'inner' is used by more than one step (CATALOG_DUPLICATE_STEP_ID)."]

    def test_validate_duplicate_input_alias_reports_error(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: two inputs declaring the same alias report CATALOG_DUPLICATE_INPUT_ALIAS."""
        _write_yaml(
            isolated_workspace / "alias.yml",
            {
                "name": "alias-dup",
                "inputs": {
                    "foo": {"type": "string", "aliases": ["-f"]},
                    "bar": {"type": "string", "aliases": ["-f"]},
                },
                "steps": [{"id": "s1", "run": "echo hi"}],
            },
        )

        result = _validate("alias.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.INVALID,
                valid=False,
                target="alias.yml",
                resolved_path=isolated_workspace / "alias.yml",
                item_type="blueprint",
                errors=["Alias '-f' is declared by both 'foo' and 'bar' (CATALOG_DUPLICATE_INPUT_ALIAS)."],
                warnings=[],
                fixes=["Resolve: Alias '-f' is declared by both 'foo' and 'bar' (CATALOG_DUPLICATE_INPUT_ALIAS)."],
            ),
        )

    def test_validate_undeclared_placeholder_reports_warning(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: '${{ inputs.missing }}' with no declared 'missing' input reports CATALOG_UNDECLARED_INPUT_PLACEHOLDER warning; status stays OK."""
        _write_yaml(
            isolated_workspace / "ph.yml",
            {"name": "ph", "steps": [{"id": "s1", "run": "echo ${{ inputs.missing }}"}]},
        )

        result = _validate("ph.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.OK,
                valid=True,
                target="ph.yml",
                resolved_path=isolated_workspace / "ph.yml",
                item_type="blueprint",
                errors=[],
                warnings=[
                    "Placeholder 'inputs.missing' is not declared in 'inputs:' (CATALOG_UNDECLARED_INPUT_PLACEHOLDER)."
                ],
                fixes=[],
            ),
        )

    def test_validate_unsafe_script_path_reports_error(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: script_path='../escape.sh' reports CATALOG_UNSAFE_SCRIPT_PATH error."""
        _write_yaml(
            isolated_workspace / "script.yml",
            {"name": "s", "steps": [{"id": "s1", "type": "script", "script_path": "../escape.sh"}]},
        )

        result = _validate("script.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.INVALID,
                valid=False,
                target="script.yml",
                resolved_path=isolated_workspace / "script.yml",
                item_type="blueprint",
                errors=[
                    "Step 's1' script_path '../escape.sh' is not a safe relative path (CATALOG_UNSAFE_SCRIPT_PATH)."
                ],
                warnings=[],
                fixes=[
                    "Resolve: Step 's1' script_path '../escape.sh' is not a safe relative path "
                    "(CATALOG_UNSAFE_SCRIPT_PATH)."
                ],
            ),
        )

    def test_validate_missing_script_file_reports_warning(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: safe but nonexistent script_path reports CATALOG_SCRIPT_NOT_FOUND warning; status stays OK."""
        _write_yaml(
            isolated_workspace / "missing_script.yml",
            {"name": "s", "steps": [{"id": "s1", "type": "script", "script_path": "scripts/none.sh"}]},
        )

        result = _validate("missing_script.yml", path=isolated_workspace, item_type=CatalogItemType.BLUEPRINT)

        assert_model_equal(
            result,
            CatalogValidateResult(
                status=CatalogValidateStatus.OK,
                valid=True,
                target="missing_script.yml",
                resolved_path=isolated_workspace / "missing_script.yml",
                item_type="blueprint",
                errors=[],
                warnings=["Step 's1' script_path 'scripts/none.sh' does not exist on disk (CATALOG_SCRIPT_NOT_FOUND)."],
                fixes=[],
            ),
        )

    def test_validate_valid_blueprint_returns_ok_status(self, isolated_workspace: Path) -> None:
        """[tier-1/domain] Catalog.validate: fully valid indexed blueprint returns status=OK, valid=True, errors=[]."""
        write_runnable_blueprint(isolated_workspace, key="clean-flow", steps=[{"id": "s1", "run": "echo hi"}])

        result = _validate("clean-flow", path=isolated_workspace)

        assert result.status == CatalogValidateStatus.OK
        assert result.valid is True
        assert result.errors == []
        assert result.ok is True

    def test_validate_result_ok_property_requires_valid_and_no_errors(self) -> None:
        """[tier-1/domain] CatalogValidateResult.ok: False when valid=True but errors is non-empty."""
        result = CatalogValidateResult(
            status=CatalogValidateStatus.OK,
            valid=True,
            target="x",
            errors=["boom"],
        )

        assert result.ok is False
