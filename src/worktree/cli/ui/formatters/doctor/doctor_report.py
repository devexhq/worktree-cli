"""ComponentFormatter for DoctorReport."""

from __future__ import annotations

from typing import Any, Final

from rich.console import Group
from rich.table import Table
from rich.text import Text

from worktree.cli.ui.formatters.doctor.doctor_views import DoctorCheckView, DoctorReportView
from worktree.common.types import ComponentFormatter
from worktree.core.doctor import CheckStatus, DoctorReport

_STATUS_STYLE: Final[dict[CheckStatus, str]] = {
    CheckStatus.OK: "green",
    CheckStatus.WARNING: "yellow",
    CheckStatus.FAILED: "red",
    CheckStatus.SKIPPED: "dim",
}


def _status_cell(status: CheckStatus) -> Text:
    """Return the upper-cased, severity-colored Status cell for one check row."""
    return Text(status.value.upper(), style=_STATUS_STYLE[status])


def _build_checks_table(view: DoctorReportView) -> Table:
    """Return a 'Worktree Doctor Report'-titled table with Check/Category/Status/Message columns, one row per view.checks entry in order."""
    table = Table(title="Worktree Doctor Report", title_justify="left", show_header=True)
    table.add_column("Check")
    table.add_column("Category")
    table.add_column("Status")
    table.add_column("Message")

    for check in view.checks:
        table.add_row(check.check_id, check.category.value, _status_cell(check.status), check.message)

    return table


def _summary_line(view: DoctorReportView) -> str:
    """Return '{n} checks: {ok} ok, {warning} warning, {failed} failed ({total_duration_ms:.1f}ms)' counted from view.checks."""
    ok_count = sum(1 for check in view.checks if check.status == CheckStatus.OK)
    warning_count = sum(1 for check in view.checks if check.status == CheckStatus.WARNING)
    failed_count = sum(1 for check in view.checks if check.status == CheckStatus.FAILED)
    return (
        f"{len(view.checks)} checks: {ok_count} ok, {warning_count} warning, "
        f"{failed_count} failed ({view.total_duration_ms:.1f}ms)"
    )


def _fix_bullets(view: DoctorReportView) -> list[str]:
    """Return one '  • {check_id}: {fix}' string per (check_id, fix) pair in view.checks order."""
    return [f"  • {check.check_id}: {fix}" for check in view.checks for fix in check.fixes]


class DoctorReportFormatter(ComponentFormatter[DoctorReport, DoctorReportView]):
    """Formatter for aggregated diagnostic doctor reports."""

    def transform(self, data: DoctorReport) -> DoctorReportView:
        """Reshape DoctorReport and its DiagnosticCheckResult entries into DoctorReportView/DoctorCheckView, field for field."""
        return DoctorReportView(
            ok=data.ok,
            has_warnings=data.has_warnings,
            workspace_root=data.workspace_root,
            total_duration_ms=data.total_duration_ms,
            checks=[
                DoctorCheckView(
                    check_id=check.check_id,
                    name=check.name,
                    category=check.category,
                    status=check.status,
                    message=check.message,
                    details=check.details,
                    duration_ms=check.duration_ms,
                    error_code=check.error_code,
                    errors=check.errors,
                    warnings=check.warnings,
                    fixes=check.fixes,
                )
                for check in data.checks
            ],
        )

    def to_rich(self, data: DoctorReport) -> Any:
        """Render the checks table, summary line, and (when any check has fixes) a Fixes: bullet section from transform(data)."""
        view = self.transform(data)
        renderables: list[Any] = [_build_checks_table(view), Text(_summary_line(view))]

        fix_bullets = _fix_bullets(view)
        if fix_bullets:
            renderables.append(Text("Fixes:"))
            renderables.extend(Text(bullet) for bullet in fix_bullets)

        return Group(*renderables)
