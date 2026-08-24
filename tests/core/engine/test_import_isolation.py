"""Regression tests for clean module import isolation and circular import prevention."""

from __future__ import annotations

import subprocess
import sys


def test_import_engine_resumable_in_isolation() -> None:
    """Ensure importing worktree.core.engine.resumable directly does not crash on circular imports."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from worktree.core.engine.resumable import ResumableRun; assert ResumableRun is not None",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Import failed with stderr: {result.stderr}"


def test_import_engine_in_isolation() -> None:
    """Ensure importing worktree.core.engine directly does not crash."""
    result = subprocess.run(
        [sys.executable, "-c", "from worktree.core.engine import Engine, BlueprintRunService, BlueprintResumeService"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Import failed with stderr: {result.stderr}"


def test_blueprint_package_does_not_import_runtime_or_engine() -> None:
    """Verify that importing worktree.core.blueprint does not load runtime or engine."""
    script = (
        "import sys\n"
        "import worktree.core.blueprint\n"
        "assert 'worktree.core.runtime' not in sys.modules, 'worktree.core.runtime was eagerly loaded'\n"
        "assert 'worktree.core.engine' not in sys.modules, 'worktree.core.engine was eagerly loaded'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Isolation test failed with stderr: {result.stderr}"
