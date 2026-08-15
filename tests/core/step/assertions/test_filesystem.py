"""Unit tests for filesystem assertion evaluators."""

from pathlib import Path

from getworktree.core.step.assertions import (
    evaluate_file_exists,
    evaluate_file_not_empty,
    evaluate_file_not_exists,
)
from tests.helpers import FileSystem


def _write(fs: FileSystem, rel_path: str, content: str = "payload") -> None:
    fs.write_file(rel_path, content)


def _mkdir(fs: FileSystem, rel_path: str) -> Path:
    path = fs.base_path / rel_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _symlink(fs: FileSystem, link_name: str, target: Path) -> Path:
    link = fs.base_path / link_name
    link.symlink_to(target)
    return link


def _missing_root(fs: FileSystem) -> Path:
    return fs.base_path / "no-such-sandbox"


class TestEvaluateFileExists:
    def test_pass_scalar(self, fs: FileSystem):
        _write(fs, "dist/app.bin")
        assert evaluate_file_exists("dist/app.bin", fs.base_path) == []

    def test_pass_list(self, fs: FileSystem):
        _write(fs, "dist/app.bin")
        _write(fs, "dist/manifest.json", "{}")
        assert evaluate_file_exists(["dist/app.bin", "dist/manifest.json"], fs.base_path) == []

    def test_missing(self, fs: FileSystem):
        assert evaluate_file_exists("dist/missing.bin", fs.base_path) == [
            "file_exists: path 'dist/missing.bin' does not exist"
        ]

    def test_directory(self, fs: FileSystem):
        _mkdir(fs, "dist")
        assert evaluate_file_exists("dist", fs.base_path) == ["file_exists: path 'dist' is a directory, not a file"]

    def test_root_escape(self, fs: FileSystem):
        assert evaluate_file_exists("../outside.txt", fs.base_path) == [
            "file_exists: path '../outside.txt' escapes the root path"
        ]

    def test_preserves_order_and_duplicates(self, fs: FileSystem):
        assert evaluate_file_exists(["missing-a", "missing-b", "missing-a"], fs.base_path) == [
            "file_exists: path 'missing-a' does not exist",
            "file_exists: path 'missing-b' does not exist",
            "file_exists: path 'missing-a' does not exist",
        ]

    def test_empty_list(self, fs: FileSystem):
        assert evaluate_file_exists([], fs.base_path) == []

    def test_missing_root_does_not_raise(self, fs: FileSystem):
        assert evaluate_file_exists("a.txt", _missing_root(fs)) == ["file_exists: path 'a.txt' does not exist"]

    def test_broken_symlink(self, fs: FileSystem):
        _symlink(fs, "broken.link", fs.base_path / "gone.txt")
        assert evaluate_file_exists("broken.link", fs.base_path) == ["file_exists: path 'broken.link' does not exist"]

    def test_symlink_escape(self, fs: FileSystem):
        outside = fs.base_path.parent / "outside-secret.txt"
        outside.write_text("secret", encoding="utf-8")
        _symlink(fs, "escape.link", outside)
        assert evaluate_file_exists("escape.link", fs.base_path) == [
            "file_exists: path 'escape.link' escapes the root path"
        ]


class TestEvaluateFileNotExists:
    def test_pass_missing(self, fs: FileSystem):
        assert evaluate_file_not_exists("tmp/lock", fs.base_path) == []

    def test_fail_file(self, fs: FileSystem):
        _write(fs, "tmp/lock", "")
        assert evaluate_file_not_exists("tmp/lock", fs.base_path) == [
            "file_not_exists: path 'tmp/lock' exists but must not"
        ]

    def test_fail_directory(self, fs: FileSystem):
        _mkdir(fs, "tmp")
        assert evaluate_file_not_exists("tmp", fs.base_path) == ["file_not_exists: path 'tmp' exists but must not"]

    def test_root_escape(self, fs: FileSystem):
        assert evaluate_file_not_exists("../outside.txt", fs.base_path) == [
            "file_not_exists: path '../outside.txt' escapes the root path"
        ]

    def test_missing_root_passes(self, fs: FileSystem):
        assert evaluate_file_not_exists("a.txt", _missing_root(fs)) == []

    def test_empty_list(self, fs: FileSystem):
        assert evaluate_file_not_exists([], fs.base_path) == []


class TestEvaluateFileNotEmpty:
    def test_pass(self, fs: FileSystem):
        _write(fs, "dist/report.txt", "ok")
        assert evaluate_file_not_empty("dist/report.txt", fs.base_path) == []

    def test_missing(self, fs: FileSystem):
        assert evaluate_file_not_empty("dist/report.txt", fs.base_path) == [
            "file_not_empty: path 'dist/report.txt' does not exist"
        ]

    def test_directory(self, fs: FileSystem):
        _mkdir(fs, "dist")
        assert evaluate_file_not_empty("dist", fs.base_path) == [
            "file_not_empty: path 'dist' is a directory, not a file"
        ]

    def test_zero_bytes(self, fs: FileSystem):
        _write(fs, "dist/report.txt", "")
        assert evaluate_file_not_empty("dist/report.txt", fs.base_path) == [
            "file_not_empty: path 'dist/report.txt' is empty (0 bytes)"
        ]

    def test_root_escape(self, fs: FileSystem):
        assert evaluate_file_not_empty("../outside.txt", fs.base_path) == [
            "file_not_empty: path '../outside.txt' escapes the root path"
        ]

    def test_list_preserves_order(self, fs: FileSystem):
        _write(fs, "empty.txt", "")
        _mkdir(fs, "dir")
        assert evaluate_file_not_empty(["missing.txt", "empty.txt", "dir"], fs.base_path) == [
            "file_not_empty: path 'missing.txt' does not exist",
            "file_not_empty: path 'empty.txt' is empty (0 bytes)",
            "file_not_empty: path 'dir' is a directory, not a file",
        ]

    def test_empty_list(self, fs: FileSystem):
        assert evaluate_file_not_empty([], fs.base_path) == []

    def test_missing_root_does_not_raise(self, fs: FileSystem):
        assert evaluate_file_not_empty("a.txt", _missing_root(fs)) == ["file_not_empty: path 'a.txt' does not exist"]

    def test_broken_symlink(self, fs: FileSystem):
        _symlink(fs, "broken.link", fs.base_path / "gone.txt")
        assert evaluate_file_not_empty("broken.link", fs.base_path) == [
            "file_not_empty: path 'broken.link' does not exist"
        ]
