# tests/cli/history/conftest.py
"""Shared workspace fixture for wt history CLI integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.builders import WorkspaceBuilder


@pytest.fixture
def history_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized git workspace (config, db, catalog) for wt history CLI tests."""
    return WorkspaceBuilder(tmp_path / "workspace").with_git().with_database().build()
