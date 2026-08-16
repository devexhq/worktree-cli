"""Unit tests for step definition YAML loading helpers."""

from pathlib import Path

import pytest

from getworktree.common.fs import get_catalog_templates_dir
from getworktree.core.catalog.services.seeder import seed_catalog_templates
from getworktree.core.db import CatalogItemType
from getworktree.core.step import (
    StepDefinition,
    StepNotFoundError,
    StepType,
    StepValidationError,
    load_step_by_id,
    load_step_definition,
)
from getworktree.core.step.services.resolver import resolve_step_definition
from tests.helpers import FileSystem

_PACKAGED_STEP_NAMES = (
    "git-sync-base",
    "ai-planner",
    "ai-code-patcher",
    "run-tests",
    "ai-reviewer",
)


def test_load_step_definition_valid(fs: FileSystem):
    step_file = fs.write_file(
        "step_verify.yaml",
        """
id: step_verify
name: verify-build
type: command
description: Run build verification
command: inv test
timeout_seconds: 300
on_failure: retry
""",
    )

    step = load_step_definition(step_file)
    assert step.id == "step_verify"
    assert step.name == "verify-build"
    assert step.type == StepType.COMMAND
    assert step.command == "inv test"
    assert step.timeout_seconds == 300
    assert step.on_failure.action.value == "retry"


def test_load_step_definition_not_found(fs: FileSystem):
    missing_path = fs.base_path / "nonexistent.yaml"
    with pytest.raises(StepNotFoundError, match="not found"):
        load_step_definition(missing_path)


def test_load_step_definition_malformed_yaml(fs: FileSystem):
    invalid_yaml = fs.write_file("invalid.yaml", "id: [unclosed list")
    with pytest.raises(StepValidationError, match="Failed to read or parse YAML"):
        load_step_definition(invalid_yaml)


def test_load_step_definition_root_not_mapping(fs: FileSystem):
    scalar_yaml = fs.write_file("scalar.yaml", "just a string")
    with pytest.raises(StepValidationError, match="must be a mapping object"):
        load_step_definition(scalar_yaml)


def test_load_step_definition_schema_validation_failure(fs: FileSystem):
    bad_schema = fs.write_file(
        "bad_schema.yaml",
        """
id: bad_step
type: command
description: Missing command field
""",
    )
    with pytest.raises(StepValidationError, match="validation failed"):
        load_step_definition(bad_schema)


def test_load_step_by_id_success(fs: FileSystem):
    fs.write_file(
        ".worktree/catalog/steps/step_lint.yaml",
        """
id: step_lint_id
name: run-lint
type: command
description: Run linter
command: ruff check .
""",
    )

    # Resolve by direct filename
    step1 = load_step_by_id("step_lint", cwd=fs.base_path)
    assert step1.id == "step_lint_id"

    # Resolve by id field
    step2 = load_step_by_id("step_lint_id", cwd=fs.base_path)
    assert step2.name == "run-lint"

    # Resolve by name slug
    step3 = load_step_by_id("run-lint", cwd=fs.base_path)
    assert step3.id == "step_lint_id"


def test_load_step_by_id_missing_directory(fs: FileSystem):
    with pytest.raises(StepNotFoundError, match=r"Directory .* does not exist"):
        load_step_by_id("step_test", cwd=fs.base_path)


def test_load_step_by_id_not_found(fs: FileSystem):
    fs.write_file(
        ".worktree/catalog/steps/other.yaml",
        """
id: other_id
name: other-name
type: command
description: Other
command: echo other
""",
    )

    with pytest.raises(StepNotFoundError, match="not found in"):
        load_step_by_id("nonexistent_step", cwd=fs.base_path)


def test_load_step_definition_returns_step_definition_instance(fs: FileSystem):
    step_file = fs.write_file("step.yaml", "id: s1\nrun: echo 1\n")
    step = load_step_definition(step_file)
    assert isinstance(step, StepDefinition)


def test_packaged_step_seeds_validate_as_step_definition():
    steps_wt = Path(str(get_catalog_templates_dir() / "steps" / "wt"))
    for name in _PACKAGED_STEP_NAMES:
        step = load_step_definition(steps_wt / f"{name}.yml")
        assert step.id == name
        assert step.name == name


def test_load_step_by_id_resolves_wt_prefix_after_seed(fs: FileSystem):
    seed_catalog_templates(CatalogItemType.STEP, cwd=fs.base_path)

    step = load_step_by_id("wt/ai-code-patcher", cwd=fs.base_path)

    assert step.id == "ai-code-patcher"
    assert step.type == StepType.AGENT
    assert step.prompt is not None


def test_load_step_by_id_scan_finds_wt_subdir_by_id(fs: FileSystem):
    seed_catalog_templates(CatalogItemType.STEP, cwd=fs.base_path)

    step = load_step_by_id("ai-code-patcher", cwd=fs.base_path)

    assert step.id == "ai-code-patcher"
    assert step.type == StepType.AGENT


def test_load_step_by_id_wt_missing_step_error(fs: FileSystem):
    (fs.base_path / ".worktree" / "catalog" / "steps").mkdir(parents=True)

    with pytest.raises(StepNotFoundError, match=r"Step 'wt/ai-code-patcher' not found in"):
        load_step_by_id("wt/ai-code-patcher", cwd=fs.base_path)


def test_load_step_by_id_direct_invalid_yaml_raises(fs: FileSystem):
    fs.write_file(".worktree/catalog/steps/wt/broken.yml", "id: [unclosed")

    with pytest.raises(StepValidationError, match="Failed to read or parse YAML"):
        load_step_by_id("wt/broken", cwd=fs.base_path)


def test_resolve_uses_wt_ai_code_patcher_after_seed(fs: FileSystem):
    seed_catalog_templates(CatalogItemType.STEP, cwd=fs.base_path)
    step = StepDefinition(id="ai-fix", uses="wt/ai-code-patcher")

    resolved = resolve_step_definition(step, cwd=fs.base_path)

    assert resolved.id == "ai-fix"
    assert resolved.type == StepType.AGENT
    assert resolved.uses is None
    assert resolved.prompt is not None
