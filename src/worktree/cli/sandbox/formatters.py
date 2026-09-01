"""ComponentFormatters for sandbox CLI domain objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.sandbox.models import SandboxListResult, SandboxShowResult, SandboxShowStatus
from worktree.cli.sandbox.renderers import build_sandbox_detail_table, build_sandbox_table
from worktree.cli.ui.dispatcher import default_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.common.utils import display_path
from worktree.core.sandbox.models import (
    PruneAction,
    PrunedItemResult,
    SandboxCreateResult,
    StaleSandboxCategory,
)

_CATEGORY_LABELS: dict[StaleSandboxCategory, str] = {
    StaleSandboxCategory.STALE_BRANCH: "stale branch",
    StaleSandboxCategory.ORPHANED_DIRECTORY: "orphaned directory",
    StaleSandboxCategory.STALE_WORKTREE_REF: "stale worktree ref",
    StaleSandboxCategory.STALE_DB_RECORD: "stale db record",
}


class PrunedItemFormatter(ComponentFormatter[PrunedItemResult]):
    """Formatter for single pruned resource items."""

    def to_rich(self, data: PrunedItemResult) -> Text:
        """Render a styled action line for a pruned resource.

        Args:
            data: Pruned resource item metadata.

        Returns:
            Styled Rich Text action line.
        """
        cat_label = _CATEGORY_LABELS.get(data.category, str(data.category.value))

        if data.action == PruneAction.PRUNED:
            if data.reason and ("would prune" in data.reason.lower() or "dry run" in data.reason.lower()):
                verb = "Would prune"
                style = self._STYLE_MAP.get("warning", "yellow")
            else:
                verb = "Pruned"
                style = self._STYLE_MAP.get("success", "green")
        elif data.action == PruneAction.SKIPPED:
            verb = "Skipped"
            style = self._STYLE_MAP.get("warning", "yellow")
        else:
            verb = "Failed to prune"
            style = self._STYLE_MAP.get("error", "red")

        content = f"• {verb} {cat_label}: {data.identifier}"
        if data.error:
            content += f" ({data.error})"

        return Text(content, style=style)

    def to_json_serializable(self, data: PrunedItemResult) -> dict[str, Any]:
        """Convert PrunedItemResult to primitive dictionary for JSON serialization.

        Args:
            data: Pruned resource item metadata.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


class SandboxShowFormatter(ComponentFormatter[SandboxShowResult]):
    """Formatter for sandbox show command results."""

    def to_rich(self, data: SandboxShowResult) -> Any:
        """Render key-value detail table or error status.

        Args:
            data: Structured result of sandbox show operation.

        Returns:
            Rich renderable object (Table, Group, Panel, or Text).
        """
        if data.ok and data.sandbox is not None:
            table = build_sandbox_detail_table(data.sandbox, disk_present=data.disk_present)
            if data.reconciled:
                return Group(
                    table,
                    Text("Note: sandbox directory is missing; status updated to 'cleaned'.", style="dim"),
                )
            return table

        if data.status == SandboxShowStatus.NOT_FOUND:
            msg = data.errors[0] if data.errors else "Sandbox not found."
            return Panel(
                f"{msg}\nFix:\n- run `wt sandbox list` to see known sandboxes",
                title="Sandbox Not Found",
                border_style="red",
            )

        err_msg = "\n\n".join(data.errors) if data.errors else "Failed to show sandbox."
        return Panel(err_msg, title="Sandbox Show Failed", border_style="red")

    def to_json_serializable(self, data: SandboxShowResult) -> dict[str, Any]:
        """Convert SandboxShowResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of sandbox show operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


class SandboxListFormatter(ComponentFormatter[SandboxListResult]):
    """Formatter for sandbox list command results."""

    def to_rich(self, data: SandboxListResult) -> Any:
        """Render sandbox summary list table or empty state.

        Args:
            data: Structured result of sandbox list operation.

        Returns:
            Rich renderable object (Table, Panel, or Text).
        """
        if not data.ok:
            err_msg = "\n\n".join(data.errors) if data.errors else "Failed to list sandboxes."
            return Panel(err_msg, title="Sandbox List Failed", border_style="red")

        if not data.sandboxes:
            return Text("No sandboxes found.")

        return build_sandbox_table(data.sandboxes)

    def to_json_serializable(self, data: SandboxListResult) -> dict[str, Any]:
        """Convert SandboxListResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of sandbox list operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


class SandboxCreateFormatter(ComponentFormatter[SandboxCreateResult]):
    """Formatter for sandbox creation command results."""

    def to_rich(self, data: SandboxCreateResult) -> Any:
        """Render sandbox creation confirmation or failure panel.

        Args:
            data: Structured result of sandbox create operation.

        Returns:
            Rich renderable object (Group, Panel, or Text).
        """
        if data.ok and data.session is not None:
            root = Path.cwd().resolve()
            path_label = display_path(data.session.sandbox_path, root)

            renderables: list[Any] = [
                Text(f"Sandbox created: {data.session.session_id}", style="green"),
                Text(f"   Branch: {data.session.target_branch}"),
                Text(f"   Path: {path_label}"),
            ]
            for warning in data.warnings:
                renderables.append(Text(f"   • {warning}", style="dim"))
            return Group(*renderables)

        err_msg = "\n\n".join(data.errors) if data.errors else "Sandbox creation failed."
        return Panel(err_msg, title="Sandbox Create Failed", border_style="red")

    def to_json_serializable(self, data: SandboxCreateResult) -> dict[str, Any]:
        """Convert SandboxCreateResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of sandbox create operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


# Register all sandbox formatters on the central default_dispatcher
default_dispatcher.register(PrunedItemResult, PrunedItemFormatter())
default_dispatcher.register(SandboxShowResult, SandboxShowFormatter())
default_dispatcher.register(SandboxListResult, SandboxListFormatter())
default_dispatcher.register(SandboxCreateResult, SandboxCreateFormatter())
