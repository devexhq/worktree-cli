"""Tests for worktree.common.version."""

from importlib import metadata

import pytest

from worktree.common.version import get_version


def test_get_version_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata, "version", lambda pkg: "1.2.3" if pkg == "worktree-cli" else "0.0.0")
    assert get_version() == "1.2.3"


def test_get_version_fallback_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_version(pkg: str) -> str:
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(metadata, "version", fake_version)
    assert get_version() == "0.1.1-local-dev"
