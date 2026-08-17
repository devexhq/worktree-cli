"""Tests for `worktree.core.patch.GitDiffParser`."""

from __future__ import annotations

from worktree.core.patch import GitDiffParser


class GitDiffParserTests:
    """Tests for GitDiffParser.parse header/path extraction."""

    def test_standard_diff_git_header(self) -> None:
        diff = "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n"

        paths, binary_paths, error = GitDiffParser(diff).parse()

        assert paths == ["foo.py"]
        assert binary_paths == []
        assert error is None

    def test_multiple_files_are_sorted(self) -> None:
        diff = "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\ndiff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"

        paths, _, error = GitDiffParser(diff).parse()

        assert paths == ["a.py", "b.py"]
        assert error is None

    def test_loose_diff_git_header_without_ab_prefixes(self) -> None:
        diff = "diff --git foo.py foo.py\n--- foo.py\n+++ foo.py\n"

        paths, _, error = GitDiffParser(diff).parse()

        assert paths == ["foo.py"]
        assert error is None

    def test_malformed_loose_diff_git_header_is_reported(self) -> None:
        diff = "diff --git foo.py\n"

        paths, binary_paths, error = GitDiffParser(diff).parse()

        assert paths == []
        assert binary_paths == []
        assert error == "malformed diff --git header"

    def test_rename_from_and_to(self) -> None:
        diff = "diff --git a/old.py b/new.py\nsimilarity index 100%\nrename from old.py\nrename to new.py\n"

        paths, _, error = GitDiffParser(diff).parse()

        assert paths == ["new.py", "old.py"]
        assert error is None

    def test_copy_from_and_to(self) -> None:
        diff = "diff --git a/old.py b/new.py\ncopy from old.py\ncopy to new.py\n"

        paths, _, error = GitDiffParser(diff).parse()

        assert paths == ["new.py", "old.py"]
        assert error is None

    def test_binary_files_header_marks_path_as_binary(self) -> None:
        diff = "diff --git a/img.png b/img.png\nBinary files a/img.png and b/img.png differ\n"

        paths, binary_paths, error = GitDiffParser(diff).parse()

        assert paths == ["img.png"]
        assert binary_paths == ["img.png"]
        assert error is None

    def test_git_binary_patch_marks_current_section_as_binary(self) -> None:
        diff = "diff --git a/img.png b/img.png\nindex 111..222 100644\nGIT binary patch\nliteral 10\n"

        paths, binary_paths, error = GitDiffParser(diff).parse()

        assert paths == ["img.png"]
        assert binary_paths == ["img.png"]
        assert error is None

    def test_literal_or_delta_line_without_known_paths_marks_unknown(self) -> None:
        diff = "--- /dev/null\n+++ /dev/null\nGIT binary patch\nliteral 10\n"

        paths, binary_paths, error = GitDiffParser(diff).parse()

        assert paths == []
        assert binary_paths == ["(unknown)"]
        assert error is None

    def test_crlf_line_endings_are_normalized(self) -> None:
        diff = "diff --git a/foo.py b/foo.py\r\n--- a/foo.py\r\n+++ b/foo.py\r\n"

        paths, _, error = GitDiffParser(diff).parse()

        assert paths == ["foo.py"]
        assert error is None

    def test_no_file_headers_is_reported(self) -> None:
        diff = "not a diff at all\njust some text\n"

        paths, binary_paths, error = GitDiffParser(diff).parse()

        assert paths == []
        assert binary_paths == []
        assert error == "no file headers found (expected diff --git or --- / +++ )"

    def test_headers_without_target_paths_is_reported(self) -> None:
        diff = "--- /dev/null\n+++ /dev/null\n"

        paths, binary_paths, error = GitDiffParser(diff).parse()

        assert paths == []
        assert binary_paths == []
        assert error == "no target file paths found in diff headers"
