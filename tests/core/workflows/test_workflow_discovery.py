"""Tests for `getworktree.core.workflows.discovery`."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from getworktree.core.config.generator import generate_default_config
from getworktree.core.workflows.discovery import (
    DEFAULT_WORKFLOWS_DIR,
    WORKFLOW_FILE_SUFFIXES,
    WorkflowDiscoveryStatus,
    discover_workflow_files,
    resolve_workflows_dir,
)
from getworktree.core.workflows.seeder import seed_starter_workflows
from tests.helpers import FileSystem


def _write_config(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


class ResolveWorkflowsDirTests:
    """Tests for resolve_workflows_dir."""

    def test_explicit_absolute_path_wins(self, fs: FileSystem) -> None:
        explicit = fs.base_path / "custom" / "workflows"
        resolved, errors = resolve_workflows_dir(cwd=fs.base_path, workflows_dir=explicit)
        assert errors == []
        assert resolved == explicit.resolve()
        assert resolved.is_absolute()

    def test_explicit_relative_path_resolves_against_cwd(self, fs: FileSystem) -> None:
        resolved, errors = resolve_workflows_dir(cwd=fs.base_path, workflows_dir="alt/workflows")
        assert errors == []
        assert resolved == (fs.base_path / "alt" / "workflows").resolve()

    def test_default_without_config(self, fs: FileSystem) -> None:
        resolved, errors = resolve_workflows_dir(cwd=fs.base_path, use_config=False)
        assert errors == []
        assert resolved == (fs.base_path / DEFAULT_WORKFLOWS_DIR).resolve()

    def test_uses_config_default_workflows_dir(self, fs: FileSystem) -> None:
        config_path = fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        result_gen = generate_default_config(config_path, "demo")
        assert result_gen.ok

        resolved, errors = resolve_workflows_dir(cwd=fs.base_path)
        assert errors == []
        assert resolved == (fs.base_path / DEFAULT_WORKFLOWS_DIR).resolve()

    def test_config_unavailable_when_missing(self, fs: FileSystem) -> None:
        resolved, errors = resolve_workflows_dir(cwd=fs.base_path, use_config=True)
        assert resolved == (fs.base_path / DEFAULT_WORKFLOWS_DIR).resolve()
        assert len(errors) == 1
        assert "WORKFLOW_CONFIG_UNAVAILABLE" in errors[0]


class DiscoverWorkflowFilesTests:
    """Tests for discover_workflow_files status and inclusion rules."""

    def test_ok_empty_directory(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()

        result = discover_workflow_files(cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.status == WorkflowDiscoveryStatus.OK
        assert result.ok
        assert result.workflows_dir == workflows_dir.resolve()
        assert result.paths == []
        assert result.errors == []

    def test_ok_seeded_layout(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / ".worktree" / "workflows"
        seed = seed_starter_workflows(workflows_dir)
        assert seed.ok

        result = discover_workflow_files(
            cwd=fs.base_path,
            workflows_dir=workflows_dir,
            use_config=False,
        )

        assert result.ok
        assert [path.name for path in result.paths] == [
            "fix-tests.yml",
            "review-fix.yml",
        ]
        assert all(path.is_absolute() for path in result.paths)

    def test_not_found(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "missing-workflows"

        result = discover_workflow_files(cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.status == WorkflowDiscoveryStatus.NOT_FOUND
        assert not result.ok
        assert result.paths == []
        assert any("WORKFLOW_DIR_NOT_FOUND" in error for error in result.errors)
        assert str(workflows_dir.resolve()) in result.errors[0]

    def test_not_a_directory(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.write_text("not a dir\n", encoding="utf-8")

        result = discover_workflow_files(cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.status == WorkflowDiscoveryStatus.NOT_A_DIRECTORY
        assert not result.ok
        assert result.paths == []
        assert any("WORKFLOW_DIR_NOT_A_DIRECTORY" in error for error in result.errors)

    def test_unreadable_directory(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        workflows_dir.chmod(0)
        try:
            result = discover_workflow_files(cwd=fs.base_path, workflows_dir=workflows_dir)
        finally:
            workflows_dir.chmod(stat.S_IRWXU)

        if os.geteuid() == 0:
            pytest.skip("root can list unreadable directories")

        assert result.status == WorkflowDiscoveryStatus.UNREADABLE
        assert not result.ok
        assert result.paths == []
        assert any("WORKFLOW_DIR_UNREADABLE" in error for error in result.errors)

    def test_config_unavailable(self, fs: FileSystem) -> None:
        result = discover_workflow_files(cwd=fs.base_path, use_config=True)

        assert result.status == WorkflowDiscoveryStatus.CONFIG_UNAVAILABLE
        assert not result.ok
        assert result.paths == []
        assert any("WORKFLOW_CONFIG_UNAVAILABLE" in error for error in result.errors)
        assert result.workflows_dir == (fs.base_path / DEFAULT_WORKFLOWS_DIR).resolve()

    def test_extension_filtering_and_sort_order(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        (workflows_dir / "b.yaml").write_text("b\n", encoding="utf-8")
        (workflows_dir / "a.yml").write_text("a\n", encoding="utf-8")
        (workflows_dir / "fix-tests.yml").write_text("f\n", encoding="utf-8")
        (workflows_dir / "readme.md").write_text("docs\n", encoding="utf-8")
        (workflows_dir / "notes.json").write_text("{}\n", encoding="utf-8")
        (workflows_dir / "nested.yml.bak").write_text("bak\n", encoding="utf-8")

        result = discover_workflow_files(cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.ok
        assert [path.name for path in result.paths] == [
            "a.yml",
            "b.yaml",
            "fix-tests.yml",
        ]
        assert all(path.suffix in WORKFLOW_FILE_SUFFIXES for path in result.paths)

    def test_ignore_hidden_private_and_subdirs(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        (workflows_dir / ".hidden.yml").write_text("h\n", encoding="utf-8")
        (workflows_dir / "_private.yml").write_text("p\n", encoding="utf-8")
        (workflows_dir / "subdir").mkdir()
        (workflows_dir / "subdir" / "nested.yml").write_text("n\n", encoding="utf-8")
        (workflows_dir / "keep.yml").write_text("k\n", encoding="utf-8")

        result = discover_workflow_files(cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.ok
        assert [path.name for path in result.paths] == ["keep.yml"]

    def test_skips_broken_symlink_without_failing(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "workflows"
        workflows_dir.mkdir()
        (workflows_dir / "good.yml").write_text("g\n", encoding="utf-8")
        broken = workflows_dir / "broken.yml"
        broken.symlink_to(fs.base_path / "missing-target.yml")

        result = discover_workflow_files(cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.ok
        assert [path.name for path in result.paths] == ["good.yml"]

    def test_explicit_override_does_not_require_config(self, fs: FileSystem) -> None:
        workflows_dir = fs.base_path / "only-workflows"
        workflows_dir.mkdir()
        (workflows_dir / "z.yml").write_text("z\n", encoding="utf-8")

        result = discover_workflow_files(cwd=fs.base_path, workflows_dir=workflows_dir)

        assert result.ok
        assert [path.name for path in result.paths] == ["z.yml"]

    def test_uses_config_when_no_explicit_dir(self, fs: FileSystem) -> None:
        config_path = fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        assert generate_default_config(config_path, "demo").ok
        workflows_dir = fs.base_path / ".worktree" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        (workflows_dir / "one.yaml").write_text("1\n", encoding="utf-8")

        result = discover_workflow_files(cwd=fs.base_path)

        assert result.ok
        assert result.workflows_dir == workflows_dir.resolve()
        assert [path.name for path in result.paths] == ["one.yaml"]
