"""Shared workspace fixture for sandbox CLI integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.builders import WorkspaceBuilder


@pytest.fixture
def sandbox_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized workspace (git, config, db, catalog) for sandbox CLI tests."""
    return WorkspaceBuilder(tmp_path / "workspace").with_git().with_database().build()
