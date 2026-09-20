"""Shared workspace fixture for doctor CLI integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.builders import WorkspaceBuilder


@pytest.fixture
def doctor_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized, healthy git+config workspace for doctor diagnostics."""
    return WorkspaceBuilder(tmp_path / "workspace").with_git().with_database().build()
