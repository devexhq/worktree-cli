"""Tests for `worktree.core.bootstrap.facade`."""

from __future__ import annotations

from tests.helpers import GitFileSystem
from worktree.core.bootstrap.facade import Bootstrap


def test_bootstrap_facade_methods(git_fs: GitFileSystem) -> None:
    facade = Bootstrap(git_fs.base_path)
    assert facade.path == git_fs.base_path.resolve()

    # Test bootstrap
    bootstrap_result = facade.bootstrap(tool_version="0.1.1")
    assert bootstrap_result.ok
    assert bootstrap_result.root_created

    # Test initialize
    init_result = facade.initialize(tool_version="0.1.1")
    assert init_result.ok
    assert init_result.config_result is not None
