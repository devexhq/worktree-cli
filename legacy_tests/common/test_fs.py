"""Unit tests for worktree.common.filesystem module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.helpers import FileSystem
from worktree.common.filesystem import Filesystem


class ScanYamlDirectoryTests:
    """Tests for scan_yaml_directory."""

    def test_nonexistent_directory_returns_empty_list(self, fs: FileSystem) -> None:
        assert Filesystem.scan_yaml_directory(fs.base_path / "missing") == []

    def test_parses_yaml_file(self, fs: FileSystem) -> None:
        (fs.base_path / "a.yml").write_text("name: My Blueprint\nkey: value\n", encoding="utf-8")

        entries = Filesystem.scan_yaml_directory(fs.base_path)

        assert len(entries) == 1
        entry = entries[0]
        assert entry.path == fs.base_path / "a.yml"
        assert entry.name == "My Blueprint"
        assert entry.parsed == {"name": "My Blueprint", "key": "value"}
        assert entry.content == "name: My Blueprint\nkey: value\n"
        assert entry.error is None

    def test_uses_name_field_when_present(self, fs: FileSystem) -> None:
        (fs.base_path / "a.yml").write_text("name: My Blueprint\nkey: value\n", encoding="utf-8")

        entries = Filesystem.scan_yaml_directory(fs.base_path)

        assert len(entries) == 1
        entry = entries[0]
        assert entry.name == "My Blueprint"
        assert entry.parsed == {"name": "My Blueprint", "key": "value"}

    def test_falls_back_to_file_stem_when_no_name_field(self, fs: FileSystem) -> None:
        (fs.base_path / "no-name.yaml").write_text("key: value\n", encoding="utf-8")

        entries = Filesystem.scan_yaml_directory(fs.base_path)

        assert len(entries) == 1
        assert entries[0].name == "no-name"

    def test_sorted_by_filename(self, fs: FileSystem) -> None:
        (fs.base_path / "b.yml").write_text("name: b\n", encoding="utf-8")
        (fs.base_path / "a.yaml").write_text("name: a\n", encoding="utf-8")
        (fs.base_path / "c.yaml").write_text("name: c\n", encoding="utf-8")

        entries = Filesystem.scan_yaml_directory(fs.base_path)

        assert [e.path.name for e in entries] == ["a.yaml", "b.yml", "c.yaml"]

    def test_ignores_non_yaml_files(self, fs: FileSystem) -> None:
        (fs.base_path / "ignore.txt").write_text("not yaml\n", encoding="utf-8")

        entries = Filesystem.scan_yaml_directory(fs.base_path)

        assert [e.path.name for e in entries] == []

    def test_unparseable_yaml_has_no_error_and_no_parsed_value(self, fs: FileSystem) -> None:
        (fs.base_path / "bad.yml").write_text("key: [unterminated\n", encoding="utf-8")

        entries = Filesystem.scan_yaml_directory(fs.base_path)

        assert len(entries) == 1
        entry = entries[0]
        assert entry.parsed is None
        assert entry.error is None
        assert entry.name == "bad"
        assert entry.content == "key: [unterminated\n"

    def test_read_failure_sets_error_and_leaves_parsed_none(self, fs: FileSystem) -> None:
        (fs.base_path / "unreadable.yml").write_text("name: test\n", encoding="utf-8")

        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            entries = Filesystem.scan_yaml_directory(fs.base_path)

        assert len(entries) == 1
        entry = entries[0]
        assert entry.parsed is None
        assert entry.error is not None
        assert "unreadable.yml" in entry.error
        assert "permission denied" in entry.error

    def test_custom_suffixes_are_respected(self, fs: FileSystem) -> None:
        (fs.base_path / "a.yml").write_text("name: a\n", encoding="utf-8")
        (fs.base_path / "b.myyaml").write_text("name: b\n", encoding="utf-8")

        entries = Filesystem.scan_yaml_directory(fs.base_path, suffixes=(".myyaml",))

        assert [e.path.name for e in entries] == ["b.myyaml"]


class AtomicWriteJsonTests:
    """Tests for atomic_write_json behavior and guarantees."""

    def test_creates_parent_directory_if_missing(self, fs: FileSystem) -> None:
        target = fs.base_path / "nested" / "deeply" / "config.json"
        data = {"key": "value"}
        Filesystem.atomic_write_json(target, data)
        assert target.exists()
        assert json.loads(target.read_text(encoding="utf-8")) == data

    def test_writes_formatted_json_with_trailing_newline(self, fs: FileSystem) -> None:
        target = fs.base_path / "config.json"
        data = {"b": 2, "a": 1}
        Filesystem.atomic_write_json(target, data)
        text = target.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert json.loads(text) == data

    def test_temp_file_sibling_location_and_cleanup(self, fs: FileSystem) -> None:
        target = fs.base_path / "config.json"
        data = {"test": True}
        tmp_path_expected = target.with_name("config.json.tmp")

        Filesystem.atomic_write_json(target, data)

        assert target.exists()
        assert not tmp_path_expected.exists()

    def test_calls_fsync_before_replace(self, fs: FileSystem) -> None:
        target = fs.base_path / "config.json"
        data = {"fsync": "check"}

        with patch("os.fsync") as mock_fsync:
            Filesystem.atomic_write_json(target, data)

            assert mock_fsync.called
            assert mock_fsync.call_count == 1

    def test_failure_during_write_cleans_up_temp_file_and_leaves_target_intact(self, fs: FileSystem) -> None:
        target = fs.base_path / "config.json"
        original_data = {"version": 1, "status": "original"}
        Filesystem.atomic_write_json(target, original_data)

        new_data = {"version": 2, "status": "new"}

        with patch("os.fsync", side_effect=OSError("Disk write failure")):
            with pytest.raises(OSError, match="Disk write failure"):
                Filesystem.atomic_write_json(target, new_data)

        # Target file must remain unchanged
        assert json.loads(target.read_text(encoding="utf-8")) == original_data

        # Temp file must be cleaned up
        temp_file = target.with_name("config.json.tmp")
        assert not temp_file.exists()
