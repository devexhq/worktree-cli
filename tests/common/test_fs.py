"""Unit tests for getworktree.common.fs module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from getworktree.common.fs import atomic_write_json


class AtomicWriteJsonTests:
    """Tests for atomic_write_json behavior and guarantees."""

    def test_creates_parent_directory_if_missing(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "deeply" / "config.json"
        data = {"key": "value"}
        atomic_write_json(target, data)
        assert target.exists()
        assert json.loads(target.read_text(encoding="utf-8")) == data

    def test_writes_formatted_json_with_trailing_newline(self, tmp_path: Path) -> None:
        target = tmp_path / "config.json"
        data = {"b": 2, "a": 1}
        atomic_write_json(target, data)
        text = target.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert json.loads(text) == data

    def test_temp_file_sibling_location_and_cleanup(self, tmp_path: Path) -> None:
        target = tmp_path / "config.json"
        data = {"test": True}
        tmp_path_expected = target.with_name("config.json.tmp")

        atomic_write_json(target, data)

        assert target.exists()
        assert not tmp_path_expected.exists()

    def test_calls_fsync_before_replace(self, tmp_path: Path) -> None:
        target = tmp_path / "config.json"
        data = {"fsync": "check"}

        with patch("os.fsync") as mock_fsync:
            atomic_write_json(target, data)

            assert mock_fsync.called
            assert mock_fsync.call_count == 1

    def test_failure_during_write_cleans_up_temp_file_and_leaves_target_intact(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "config.json"
        original_data = {"version": 1, "status": "original"}
        atomic_write_json(target, original_data)

        new_data = {"version": 2, "status": "new"}

        with patch("os.fsync", side_effect=OSError("Disk write failure")):
            with pytest.raises(OSError, match="Disk write failure"):
                atomic_write_json(target, new_data)

        # Target file must remain unchanged
        assert json.loads(target.read_text(encoding="utf-8")) == original_data

        # Temp file must be cleaned up
        temp_file = target.with_name("config.json.tmp")
        assert not temp_file.exists()
