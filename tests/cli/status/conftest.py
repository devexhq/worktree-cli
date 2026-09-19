"""Shared workspace fixture for status CLI integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.builders import WorkspaceBuilder


@pytest.fixture
def status_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized workspace without catalog templates for deterministic status counts."""
    return WorkspaceBuilder(tmp_path / "workspace").with_git().with_database().without_catalog_templates().build()
