"""Diagnostic check registry and execution engine."""

from worktree.core.doctor.doctor import Doctor
from worktree.core.doctor.exceptions import CheckRegistrationError, DoctorError
from worktree.core.doctor.models import (
    CheckCategory,
    CheckStatus,
    DiagnosticCheck,
    DiagnosticCheckResult,
    DoctorContext,
    DoctorReport,
    Remediation,
    RemediationType,
)

__all__ = [
    "CheckCategory",
    "CheckRegistrationError",
    "CheckStatus",
    "DiagnosticCheck",
    "DiagnosticCheckResult",
    "Doctor",
    "DoctorContext",
    "DoctorError",
    "DoctorReport",
    "Remediation",
    "RemediationType",
]
