"""Tests for `getworktree.core.workflows.metadata`."""

from __future__ import annotations

import os
import stat
from importlib import resources
from pathlib import Path

import pytest

from getworktree.core.workflows.metadata import (
    WorkflowMetadataStatus,
    parse_workflow_metadata,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _template_text(name: str) -> str:
    root = resources.files("getworktree.core.templates.workflows")
    with root.joinpath(name).open(encoding="utf-8") as handle:
        return handle.read()


class ParseWorkflowMetadataTests:
    """Tests for parse_workflow_metadata statuses and field codes."""

    def test_ok_on_packaged_fix_tests_template(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "fix-tests.yml", _template_text("fix-tests.yml"))

        result = parse_workflow_metadata(path)

        assert result.status == WorkflowMetadataStatus.OK
        assert result.ok
        assert result.errors == []
        assert result.metadata is not None
        assert result.metadata.version == 1
        assert result.metadata.name == "fix-tests"
        assert "failing tests" in result.metadata.description
        assert result.metadata.source_path == path.resolve()
        assert result.source_path == path.resolve()

    def test_ok_on_packaged_review_fix_template(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "review-fix.yml", _template_text("review-fix.yml"))

        result = parse_workflow_metadata(path)

        assert result.ok
        assert result.metadata is not None
        assert result.metadata.name == "review-fix"
        assert result.metadata.version == 1
        assert result.metadata.description.startswith("Iteratively remediate")

    def test_ok_with_extra_keys_and_incomplete_body(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "minimal.yml",
            (
                "version: 1\n"
                "name: minimal-workflow\n"
                "description: only identity fields\n"
                "extra_ignored: true\n"
            ),
        )

        result = parse_workflow_metadata(path)

        assert result.ok
        assert result.metadata is not None
        assert result.metadata.name == "minimal-workflow"

    def test_not_found(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.yml"

        result = parse_workflow_metadata(path)

        assert result.status == WorkflowMetadataStatus.NOT_FOUND
        assert not result.ok
        assert result.metadata is None
        assert any("WORKFLOW_META_NOT_FOUND" in error for error in result.errors)

    def test_not_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "workflows-dir"
        path.mkdir()

        result = parse_workflow_metadata(path)

        assert result.status == WorkflowMetadataStatus.NOT_A_FILE
        assert not result.ok
        assert any("WORKFLOW_META_NOT_A_FILE" in error for error in result.errors)

    def test_unreadable(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "secret.yml", "version: 1\n")
        path.chmod(0)
        try:
            result = parse_workflow_metadata(path)
        finally:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        if os.geteuid() == 0:
            pytest.skip("root can read unreadable files")

        assert result.status == WorkflowMetadataStatus.UNREADABLE
        assert not result.ok
        assert any("WORKFLOW_META_UNREADABLE" in error for error in result.errors)

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "broken.yml", "version: [\n")

        result = parse_workflow_metadata(path)

        assert result.status == WorkflowMetadataStatus.MALFORMED_YAML
        assert not result.ok
        assert any("WORKFLOW_META_MALFORMED_YAML" in error for error in result.errors)

    def test_root_not_mapping_null_and_list(self, tmp_path: Path) -> None:
        empty = _write(tmp_path / "empty.yml", "")
        listed = _write(tmp_path / "list.yml", "- a\n- b\n")

        empty_result = parse_workflow_metadata(empty)
        list_result = parse_workflow_metadata(listed)

        assert empty_result.status == WorkflowMetadataStatus.ROOT_NOT_MAPPING
        assert list_result.status == WorkflowMetadataStatus.ROOT_NOT_MAPPING
        assert any(
            "WORKFLOW_META_ROOT_NOT_MAPPING" in error for error in empty_result.errors
        )
        assert any(
            "WORKFLOW_META_ROOT_NOT_MAPPING" in error for error in list_result.errors
        )

    def test_collects_all_missing_field_codes(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "blank.yml", "other: 1\n")

        result = parse_workflow_metadata(path)

        assert result.status == WorkflowMetadataStatus.INVALID_METADATA
        joined = "\n".join(result.errors)
        assert "WORKFLOW_META_MISSING_VERSION" in joined
        assert "WORKFLOW_META_MISSING_NAME" in joined
        assert "WORKFLOW_META_MISSING_DESCRIPTION" in joined

    def test_invalid_version_variants(self, tmp_path: Path) -> None:
        cases = (
            "version: 2\nname: ok-name\ndescription: d\n",
            'version: "1"\nname: ok-name\ndescription: d\n',
            "version: true\nname: ok-name\ndescription: d\n",
        )
        for index, text in enumerate(cases):
            path = _write(tmp_path / f"bad-version-{index}.yml", text)
            result = parse_workflow_metadata(path)
            assert result.status == WorkflowMetadataStatus.INVALID_METADATA
            assert any(
                "WORKFLOW_META_INVALID_VERSION" in error for error in result.errors
            )

    def test_invalid_name_variants(self, tmp_path: Path) -> None:
        cases = (
            'version: 1\nname: "Fix Tests"\ndescription: d\n',
            'version: 1\nname: ""\ndescription: d\n',
            "version: 1\nname: 12\ndescription: d\n",
        )
        for index, text in enumerate(cases):
            path = _write(tmp_path / f"bad-name-{index}.yml", text)
            result = parse_workflow_metadata(path)
            assert result.status == WorkflowMetadataStatus.INVALID_METADATA
            assert any("WORKFLOW_META_INVALID_NAME" in error for error in result.errors)

    def test_invalid_description_variants(self, tmp_path: Path) -> None:
        cases = (
            'version: 1\nname: ok-name\ndescription: ""\n',
            "version: 1\nname: ok-name\ndescription: 1\n",
        )
        for index, text in enumerate(cases):
            path = _write(tmp_path / f"bad-desc-{index}.yml", text)
            result = parse_workflow_metadata(path)
            assert result.status == WorkflowMetadataStatus.INVALID_METADATA
            assert any(
                "WORKFLOW_META_INVALID_DESCRIPTION" in error for error in result.errors
            )

    def test_description_allows_leading_trailing_spaces(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "spaces.yml",
            "version: 1\nname: spaced\ndescription: ' padded '\n",
        )

        result = parse_workflow_metadata(path)

        assert result.ok
        assert result.metadata is not None
        assert result.metadata.description == " padded "
