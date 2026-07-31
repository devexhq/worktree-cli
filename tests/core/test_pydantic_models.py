from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from getworktree.core.bootstrap import BootstrapResult


def test_bootstrap_result_rejects_non_bool_values() -> None:
    with pytest.raises(ValidationError):
        BootstrapResult(root_path=Path("/tmp"), root_created="yes")
