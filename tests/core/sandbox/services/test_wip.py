"""Domain tests for sandbox WIP overlays."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from worktree.core.git.exceptions import GitPlumbingTimeoutError
from worktree.core.git.runner import GitRunner
from worktree.core.sandbox.exceptions import SandboxError
from worktree.core.sandbox.services.wip import (
    apply_wip_to_sandbox,
    copy_wip_file,
    list_wip_paths,
    normalize_repo_rel,
    remove_destination,
)


class NormalizeRepoRelTests:
    """Tests for repository-relative path normalization."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param("  path/to/file.txt  ", "path/to/file.txt", id="whitespace_stripped"),
            pytest.param("nested\\windows\\path.txt", "nested/windows/path.txt", id="backslashes_converted"),
            pytest.param("  nested\\both.txt  ", "nested/both.txt", id="whitespace_and_backslashes"),
            pytest.param("already/posix.txt", "already/posix.txt", id="already_clean_unchanged"),
        ],
    )
    def test_path_normalized_to_stripped_posix_form(self, raw: str, expected: str) -> None:
        """Whitespace is stripped and backslashes are converted to forward slashes."""
        assert normalize_repo_rel(raw) == expected


class WipPathListingTests:
    """Tests for the repository-relative paths selected from Git status."""

    def test_porcelain_paths_are_normalized_deduplicated_and_sorted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mixed porcelain entries return normalized unique repository-relative paths."""
        monkeypatch.setattr(
            GitRunner,
            "status_porcelain",
            staticmethod(
                lambda _: [
                    " M nested\\modified.txt",
                    "?? nested/new.txt",
                    "R  previous-name.txt -> renamed.txt",
                    '?? "quoted.txt"',
                    "?? nested/new.txt",
                ]
            ),
        )

        paths = list_wip_paths(tmp_path)

        assert paths == ["nested/modified.txt", "nested/new.txt", "quoted.txt", "renamed.txt"]

    @pytest.mark.parametrize(
        "porcelain_line",
        [
            pytest.param("??", id="too_short_no_entry_segment"),
            pytest.param('?? ""', id="empty_after_quote_and_whitespace_strip"),
        ],
    )
    def test_malformed_or_empty_entry_yields_no_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        porcelain_line: str,
    ) -> None:
        """Short or blank porcelain entries are omitted from the returned paths."""
        monkeypatch.setattr(GitRunner, "status_porcelain", staticmethod(lambda _: [porcelain_line]))

        paths = list_wip_paths(tmp_path)

        assert paths == []

    def test_no_status_lines_returns_empty_list(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An empty Git status result returns no WIP paths."""
        monkeypatch.setattr(GitRunner, "status_porcelain", staticmethod(lambda _: []))

        paths = list_wip_paths(tmp_path)

        assert paths == []


class RemoveDestinationTests:
    """Tests for removing files, directories, and symlinks from sandboxes."""

    @pytest.mark.parametrize(
        "kind",
        [
            pytest.param("regular_file", id="regular_file"),
            pytest.param("directory", id="directory_rmtree"),
            pytest.param("symlink_to_file", id="symlink_to_file_unlinked_not_target"),
            pytest.param("symlink_to_directory", id="symlink_to_directory_unlinked_not_rmtree"),
            pytest.param("broken_symlink", id="broken_symlink_unlinked"),
        ],
    )
    def test_destination_removed_according_to_its_kind(
        self,
        tmp_path: Path,
        kind: Literal[
            "regular_file",
            "directory",
            "symlink_to_file",
            "symlink_to_directory",
            "broken_symlink",
        ],
    ) -> None:
        """Files, directories, and symlinks are removed without deleting symlink targets."""
        destination = tmp_path / "destination"
        target = tmp_path / "target"
        if kind == "regular_file":
            destination.write_text("destination", encoding="utf-8")
        elif kind == "directory":
            destination.mkdir()
            (destination / "child.txt").write_text("child", encoding="utf-8")
        elif kind == "symlink_to_file":
            target.write_text("target", encoding="utf-8")
            destination.symlink_to(target)
        elif kind == "symlink_to_directory":
            target.mkdir()
            (target / "child.txt").write_text("target child", encoding="utf-8")
            destination.symlink_to(target, target_is_directory=True)
        else:
            destination.symlink_to(target)

        remove_destination(destination)

        assert not destination.exists()
        assert not destination.is_symlink()
        if kind == "symlink_to_file":
            assert target.read_text(encoding="utf-8") == "target"
        if kind == "symlink_to_directory":
            assert (target / "child.txt").read_text(encoding="utf-8") == "target child"

    def test_nonexistent_destination_is_a_no_op(self, tmp_path: Path) -> None:
        """A path that does not exist is left absent without raising an error."""
        destination = tmp_path / "missing"

        remove_destination(destination)

        assert not destination.exists()
        assert not destination.is_symlink()


class CopyWipFileTests:
    """Tests for copying individual WIP paths into a sandbox."""

    def test_directory_source_is_skipped_without_creating_destination(self, tmp_path: Path) -> None:
        """A plain directory source is skipped and creates no destination path."""
        source_root = tmp_path / "source"
        destination_root = tmp_path / "destination"
        (source_root / "directory").mkdir(parents=True)
        destination_root.mkdir()

        copy_wip_file(source_root, destination_root, "directory")

        assert not (destination_root / "directory").exists()

    def test_regular_file_source_copies_content_and_preserves_metadata(self, tmp_path: Path) -> None:
        """A regular source file is copied into new parents with its mode preserved."""
        source_root = tmp_path / "source"
        destination_root = tmp_path / "destination"
        source_file = source_root / "nested" / "source.txt"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("source content", encoding="utf-8")
        source_file.chmod(0o640)
        destination_root.mkdir()

        copy_wip_file(source_root, destination_root, "nested/source.txt")

        destination_file = destination_root / "nested" / "source.txt"
        assert destination_file.read_text(encoding="utf-8") == "source content"
        assert destination_file.stat().st_mode & 0o777 == source_file.stat().st_mode & 0o777

    def test_symlink_source_replaces_existing_destination_file_with_symlink(self, tmp_path: Path) -> None:
        """A symlink source replaces an existing destination file with the same link target."""
        source_root = tmp_path / "source"
        destination_root = tmp_path / "destination"
        source_root.mkdir()
        destination_root.mkdir()
        (source_root / "target.txt").write_text("target", encoding="utf-8")
        source_link = source_root / "link.txt"
        source_link.symlink_to("target.txt")
        destination_file = destination_root / "link.txt"
        destination_file.write_text("regular file", encoding="utf-8")

        copy_wip_file(source_root, destination_root, "link.txt")

        assert destination_file.is_symlink()
        assert destination_file.readlink() == source_link.readlink()

    def test_missing_source_removes_existing_destination(self, tmp_path: Path) -> None:
        """A missing source path removes its existing destination file."""
        source_root = tmp_path / "source"
        destination_root = tmp_path / "destination"
        source_root.mkdir()
        destination_root.mkdir()
        destination_file = destination_root / "removed.txt"
        destination_file.write_text("stale", encoding="utf-8")

        copy_wip_file(source_root, destination_root, "removed.txt")

        assert not destination_file.exists()


class WipOverlayTests:
    """Tests for observable filesystem effects of applying WIP changes."""

    def test_deleted_nested_and_symlinked_paths_update_sandbox(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Overlay removes deletions, creates nested files, and replaces paths with symlinks."""
        source_root = tmp_path / "source"
        sandbox_path = tmp_path / "sandbox"
        source_root.mkdir()
        sandbox_path.mkdir()

        (sandbox_path / "removed.txt").write_text("stale", encoding="utf-8")
        nested_file = source_root / "nested" / "created.txt"
        nested_file.parent.mkdir()
        nested_file.write_text("WIP content", encoding="utf-8")
        (source_root / "target.txt").write_text("target", encoding="utf-8")
        source_link = source_root / "links" / "target-link"
        source_link.parent.mkdir()
        source_link.symlink_to("../target.txt")
        destination_link = sandbox_path / "links" / "target-link"
        destination_link.parent.mkdir()
        destination_link.write_text("not a symlink", encoding="utf-8")

        monkeypatch.setattr(
            GitRunner,
            "status_porcelain",
            staticmethod(lambda _: [" D removed.txt", "?? nested/created.txt", "?? links/target-link"]),
        )

        paths = apply_wip_to_sandbox(source_root=source_root, sandbox_path=sandbox_path)

        assert paths == ["links/target-link", "nested/created.txt", "removed.txt"]
        assert not (sandbox_path / "removed.txt").exists()
        assert (sandbox_path / "nested" / "created.txt").read_text(encoding="utf-8") == "WIP content"
        assert destination_link.is_symlink()
        assert destination_link.readlink() == Path("../target.txt")

    def test_missing_sandbox_path_raises_sandbox_error(self, tmp_path: Path) -> None:
        """A sandbox path that is not a directory raises SandboxError with its resolved path."""
        source_root = tmp_path / "source"
        source_root.mkdir()
        sandbox_path = tmp_path / "missing-sandbox"

        with pytest.raises(SandboxError, match=f"sandbox path does not exist: {sandbox_path.resolve()}"):
            apply_wip_to_sandbox(source_root=source_root, sandbox_path=sandbox_path)

    def test_no_uncommitted_changes_returns_empty_list_and_leaves_sandbox_untouched(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An empty Git status leaves sandbox files untouched and returns no paths."""
        source_root = tmp_path / "source"
        sandbox_path = tmp_path / "sandbox"
        source_root.mkdir()
        sandbox_path.mkdir()
        sentinel = sandbox_path / "sentinel.txt"
        sentinel.write_text("unchanged", encoding="utf-8")
        monkeypatch.setattr(GitRunner, "status_porcelain", staticmethod(lambda _: []))

        paths = apply_wip_to_sandbox(source_root=source_root, sandbox_path=sandbox_path)

        assert paths == []
        assert sentinel.read_text(encoding="utf-8") == "unchanged"

    def test_oserror_during_copy_is_wrapped_as_sandbox_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A filesystem copy error is translated to SandboxError rather than propagated raw."""
        source_root = tmp_path / "source"
        sandbox_path = tmp_path / "sandbox"
        source_file = source_root / "nested" / "changed.txt"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("WIP content", encoding="utf-8")
        sandbox_path.mkdir()
        (sandbox_path / "nested").write_text("blocks directory creation", encoding="utf-8")
        monkeypatch.setattr(GitRunner, "status_porcelain", staticmethod(lambda _: ["?? nested/changed.txt"]))

        with pytest.raises(SandboxError) as error_info:
            apply_wip_to_sandbox(source_root=source_root, sandbox_path=sandbox_path)

        assert isinstance(error_info.value.__cause__, FileExistsError)
        assert "File exists" in str(error_info.value)

    def test_git_plumbing_timeout_propagates_unwrapped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A Git plumbing timeout remains a GitPlumbingTimeoutError rather than SandboxError."""
        source_root = tmp_path / "source"
        sandbox_path = tmp_path / "sandbox"
        source_root.mkdir()
        sandbox_path.mkdir()
        timeout = GitPlumbingTimeoutError("git timed out")
        monkeypatch.setattr(
            GitRunner,
            "status_porcelain",
            staticmethod(lambda _: (_ for _ in ()).throw(timeout)),
        )

        with pytest.raises(GitPlumbingTimeoutError) as error_info:
            apply_wip_to_sandbox(source_root=source_root, sandbox_path=sandbox_path)

        assert error_info.value is timeout
