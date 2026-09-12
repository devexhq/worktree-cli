"""Initial bootstrap smoke test."""

import pytest

pytestmark = pytest.mark.unit


def test_initial() -> None:
    """Initial smoke assertion verifying test runner discovery."""
    assert 1 == 1
