"""Presentation view models for DoctorReport."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from worktree.core.doctor import CheckCategory, CheckStatus


class DoctorCheckView(BaseModel):
    """Semantic view of one diagnostic check outcome: no Rich markup, no composed sentences."""

    model_config = {"extra": "forbid", "strict": True}

    check_id: str
    name: str
    category: CheckCategory
    status: CheckStatus
    message: str
    details: dict[str, Any]
    duration_ms: float
    error_code: str | None
    errors: list[str]
    warnings: list[str]
    fixes: list[str]


class DoctorReportView(BaseModel):
    """Semantic view of an aggregated doctor report: no Rich markup, no composed sentences."""

    model_config = {"extra": "forbid", "strict": True}

    ok: bool
    has_warnings: bool
    workspace_root: Path
    total_duration_ms: float
    checks: list[DoctorCheckView]
