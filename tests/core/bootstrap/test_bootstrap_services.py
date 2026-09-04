"""Tests for `worktree.core.bootstrap.services.bootstrap`."""

import json
import os
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.helpers import FileSystem
from worktree.core.bootstrap import (
    BOOTSTRAP_META_REL,
    REQUIRED_SUBDIRS,
    BootstrapResult,
    bootstrap_worktree,
)


@pytest.fixture
def project_tmp(fs: FileSystem) -> Path:
    return fs.base_path


class BootstrapWorktreeTests:
    """Tests for `bootstrap_worktree`."""

    def test_creates_full_structure_from_empty(self, project_tmp: Path):
        root = project_tmp / ".worktree"
        result = bootstrap_worktree(root, tool_version="0.1.1")

        assert result.ok
        assert result.root_created
        assert len(result.dirs_created) == len(REQUIRED_SUBDIRS)
        assert not result.dirs_existing
        assert not result.repaired

        meta = json.loads((root / BOOTSTRAP_META_REL).read_text(encoding="utf-8"))
        assert meta["schema_version"] == 1
        assert meta["status"] == "initialized"
        assert meta["tool_version"] == "0.1.1"
        assert meta["initialized_at"]

    def test_idempotent_rerun(self, project_tmp: Path):
        root = project_tmp / ".worktree"
        first = bootstrap_worktree(root)
        assert first.ok

        marker = root / "workflows" / "keep.me"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("stay", encoding="utf-8")

        second = bootstrap_worktree(root)
        assert second.ok
        assert not second.root_created
        assert not second.dirs_created
        assert not second.repaired
        assert marker.read_text(encoding="utf-8") == "stay"

    def test_partial_repair(self, project_tmp: Path):
        root = project_tmp / ".worktree"
        root.mkdir()
        (root / "workflows").mkdir()
        (root / "artifacts").mkdir()

        result = bootstrap_worktree(root)
        assert result.ok
        assert result.repaired
        assert (root / "sessions").is_dir()
        assert (root / ".meta" / "bootstrap.json").is_file()

        meta = json.loads((root / BOOTSTRAP_META_REL).read_text(encoding="utf-8"))
        assert meta["status"] == "repaired"

    def test_root_exists_as_file(self, project_tmp: Path):
        root = project_tmp / ".worktree"
        root.write_text("not a dir", encoding="utf-8")

        result = bootstrap_worktree(root)
        assert not result.ok
        assert any("file" in err.lower() for err in result.errors)

    def test_subdir_exists_as_file(self, project_tmp: Path):
        root = project_tmp / ".worktree"
        root.mkdir()
        (root / "workflows").write_text("file", encoding="utf-8")

        result = bootstrap_worktree(root)
        assert not result.ok
        assert any("workflows" in err for err in result.errors)

    def test_subdir_symlink_rejected(self, project_tmp: Path):
        root = project_tmp / ".worktree"
        root.mkdir()
        target = project_tmp / "real_workflows"
        target.mkdir()
        (root / "workflows").symlink_to(target)

        result = bootstrap_worktree(root)
        assert not result.ok
        assert any("symlink" in err.lower() for err in result.errors)

    def test_root_symlink_allowed(self, project_tmp: Path):
        target = project_tmp / "worktree_home"
        target.mkdir()
        link = project_tmp / ".worktree"
        link.symlink_to(target)

        result = bootstrap_worktree(link)
        assert result.ok
        assert (target / "sessions").is_dir()

    def test_initialized_at_stable_across_reruns(self, project_tmp: Path):
        root = project_tmp / ".worktree"
        bootstrap_worktree(root)
        first_meta = json.loads((root / BOOTSTRAP_META_REL).read_text(encoding="utf-8"))
        first_init = first_meta["initialized_at"]

        bootstrap_worktree(root)
        second_meta = json.loads((root / BOOTSTRAP_META_REL).read_text(encoding="utf-8"))
        assert second_meta["initialized_at"] == first_init
        assert second_meta["last_checked_at"] >= first_meta["last_checked_at"]

    def test_unwritable_dir(self, project_tmp: Path):
        root = project_tmp / ".worktree"
        root.mkdir()
        os.chmod(root, stat.S_IRUSR | stat.S_IXUSR)

        result = bootstrap_worktree(root)
        assert not result.ok
        assert any("writable" in err.lower() for err in result.errors)

        os.chmod(root, stat.S_IRWXU)


class BootstrapResultValidationTests:
    """Tests for the strict `BootstrapResult` model."""

    def test_bootstrap_result_rejects_non_bool_values(self) -> None:
        with pytest.raises(ValidationError):
            BootstrapResult.model_validate(
                {
                    "root_path": Path("/tmp"),
                    "root_created": "yes",
                }
            )
