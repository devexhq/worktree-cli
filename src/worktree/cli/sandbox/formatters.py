"""ComponentFormatters for sandbox CLI domain objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from worktree.cli.sandbox.renderers import build_sandbox_detail_table, build_sandbox_table
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.common.utils import display_path
from worktree.core.sandbox.models import (
    PruneAction,
    PrunedItem,
    SandboxApplyResult,
    SandboxApplyStrategy,
    SandboxCreateResult,
    SandboxDeleteResult,
    SandboxDeleteStatus,
    SandboxDiffResult,
    SandboxDiffStatus,
    SandboxListResult,
    SandboxPruneResult,
    SandboxShowResult,
    SandboxShowStatus,
    StaleSandboxCategory,
)

_CATEGORY_LABELS: dict[StaleSandboxCategory, str] = {
    StaleSandboxCategory.STALE_BRANCH: "stale branch",
    StaleSandboxCategory.ORPHANED_DIRECTORY: "orphaned directory",
    StaleSandboxCategory.STALE_WORKTREE_REF: "stale worktree ref",
    StaleSandboxCategory.STALE_DB_RECORD: "stale db record",
}


class PrunedItemFormatter(ComponentFormatter[PrunedItem]):
    """Formatter for single pruned resource items."""

    def to_rich(self, data: PrunedItem) -> Text:
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

    def to_json_serializable(self, data: PrunedItem) -> dict[str, Any]:
        """Convert PrunedItem to primitive dictionary for JSON serialization.

        Args:
            data: Pruned resource item metadata.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def _format_show_error_panel(data: SandboxShowResult) -> Panel:
    """Format error panel for non-ok sandbox show results."""
    if data.status == SandboxShowStatus.NOT_INITIALIZED:
        err_msg = "\n\n".join(data.errors) if data.errors else "Worktree workspace is not initialized."
        return Panel(
            f"{err_msg}\n\nHint: run `wt init` to create `.worktree/config.json`",
            title="Worktree Not Initialized",
            border_style="red",
        )

    if data.status == SandboxShowStatus.NOT_FOUND:
        msg = data.errors[0] if data.errors else "Sandbox not found."
        return Panel(
            f"{msg}\nFix:\n- run `wt sandbox list` to see known sandboxes",
            title="Sandbox Not Found",
            border_style="red",
        )

    err_msg = "\n\n".join(data.errors) if data.errors else "Failed to show sandbox."
    return Panel(err_msg, title="Sandbox Show Failed", border_style="red")


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

        return _format_show_error_panel(data)

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
            err_msg = "\n\n".join(data.errors) if data.errors else "Worktree workspace is not initialized."
            return Panel(
                f"{err_msg}\n\nFix:\n- run `wt init` to create `.worktree/config.json`",
                title="Worktree Not Initialized",
                border_style="red",
            )

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


def _format_apply_success(data: SandboxApplyResult) -> Group:
    """Render success block for sandbox apply."""
    strategy_label = data.strategy.value
    renderables: list[Any] = [Text(f"Applied sandbox {data.sandbox_id} to workspace ({strategy_label})", style="green")]

    if data.strategy == SandboxApplyStrategy.SQUASH and data.commit_sha:
        renderables.append(Text(f"• Commit: {data.commit_sha}", style="dim"))
    elif data.touched_files:
        files_count = len(data.touched_files)
        files_text = f"{files_count} file changed" if files_count == 1 else f"{files_count} files changed"
        renderables.append(Text(f"• {files_text}", style="dim"))

    renderables.append(Text("• Status updated: merged", style="dim"))

    if data.cleaned_up:
        renderables.append(Text("• Sandbox worktree and branch deleted", style="dim"))

    for warning in data.warnings:
        renderables.append(Text(f"• {warning}", style="dim"))

    return Group(*renderables)


class SandboxApplyFormatter(ComponentFormatter[SandboxApplyResult]):
    """Formatter for sandbox apply command results."""

    def to_rich(self, data: SandboxApplyResult) -> Any:
        """Render sandbox apply success summary or failure panel.

        Args:
            data: Structured result of sandbox apply operation.

        Returns:
            Rich renderable object (Group, Panel).
        """
        if data.ok:
            return _format_apply_success(data)

        message = "\n\n".join(data.errors) if data.errors else "Sandbox apply failed."
        return Panel(message, title="Sandbox Apply Failed", border_style="red")

    def to_json_serializable(self, data: SandboxApplyResult) -> dict[str, Any]:
        """Convert SandboxApplyResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of sandbox apply operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def _format_delete_error_panel(data: SandboxDeleteResult) -> Panel:
    """Format error panel for non-ok sandbox delete results."""
    if data.status == SandboxDeleteStatus.NOT_INITIALIZED:
        err_msg = "\n\n".join(data.errors) if data.errors else "Worktree workspace is not initialized."
        return Panel(
            f"{err_msg}\n\nFix:\n- run `wt init` to create `.worktree/config.json`",
            title="Worktree Not Initialized",
            border_style="red",
        )
    if data.status == SandboxDeleteStatus.NOT_FOUND:
        return Panel(
            f"Sandbox '{data.sandbox_id}' not found.\nFix:\n- run `wt sandbox list` to see known sandboxes",
            title="Sandbox Not Found",
            border_style="red",
        )
    message = "\n\n".join(data.errors) if data.errors else "Sandbox delete failed."
    return Panel(message, title="Sandbox Delete Failed", border_style="red")


class SandboxDeleteFormatter(ComponentFormatter[SandboxDeleteResult]):
    """Formatter for sandbox delete command results."""

    def to_rich(self, data: SandboxDeleteResult) -> Any:
        """Render sandbox delete success, aborted, or error state.

        Args:
            data: Structured result of sandbox delete operation.

        Returns:
            Rich renderable object (Text, Panel).
        """
        if data.status == SandboxDeleteStatus.ALREADY_CLEANED:
            return Text(f"Sandbox '{data.sandbox_id}' is already cleaned; nothing to remove.")
        if data.status == SandboxDeleteStatus.ABORTED:
            return Text("Aborted.")
        if data.status == SandboxDeleteStatus.DELETED or data.deleted:
            return Text(f"Sandbox deleted: {data.sandbox_id}", style="green")
        return _format_delete_error_panel(data)

    def to_json_serializable(self, data: SandboxDeleteResult) -> dict[str, Any]:
        """Convert SandboxDeleteResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of sandbox delete operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


class SandboxDiffFormatter(ComponentFormatter[SandboxDiffResult]):
    """Formatter for sandbox diff command results."""

    def to_rich(self, data: SandboxDiffResult) -> Any:
        """Render sandbox diff text, stat summary, or error panel.

        Args:
            data: Structured result of sandbox diff operation.

        Returns:
            Rich renderable object (Syntax, Text, Panel).
        """
        if data.status == SandboxDiffStatus.EMPTY_DIFF:
            return Text(f"Sandbox '{data.sandbox_id}' has no changes compared to base commit.")
        if not data.ok:
            message = "\n\n".join(data.errors) if data.errors else "Failed to generate diff."
            return Panel(message, title="Sandbox Diff Failed", border_style="red")
        if data.stat_text:
            return Text(data.stat_text.strip())
        return Syntax(data.diff_text.strip(), "diff", word_wrap=True)

    def to_json_serializable(self, data: SandboxDiffResult) -> dict[str, Any]:
        """Convert SandboxDiffResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of sandbox diff operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def _format_prune_rich(data: SandboxPruneResult) -> Any:
    """Render rich group or text for sandbox prune result."""
    if not data.items and not data.errors:
        return Text("No stale sandboxes found.")

    renderables: list[Any] = []
    item_formatter = PrunedItemFormatter()
    for item in data.items:
        renderables.append(item_formatter.to_rich(item))

    if data.errors:
        for err in data.errors:
            renderables.append(Text(f"Error: {err}", style="red"))

    return Group(*renderables)


class SandboxPruneFormatter(ComponentFormatter[SandboxPruneResult]):
    """Formatter for sandbox prune command results."""

    def to_rich(self, data: SandboxPruneResult) -> Any:
        """Render sandbox prune action lines, empty state, or errors.

        Args:
            data: Structured result of sandbox prune operation.

        Returns:
            Rich renderable object (Group, Text).
        """
        return _format_prune_rich(data)

    def to_json_serializable(self, data: SandboxPruneResult) -> dict[str, Any]:
        """Convert SandboxPruneResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of sandbox prune operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def register_sandbox_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register all sandbox ComponentFormatter instances on a UiDispatcher.

    Args:
        dispatcher: UiDispatcher instance to register on. Defaults to ui_dispatcher.
    """
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(PrunedItem, PrunedItemFormatter())
    target.register(SandboxPruneResult, SandboxPruneFormatter())
    target.register(SandboxShowResult, SandboxShowFormatter())
    target.register(SandboxListResult, SandboxListFormatter())
    target.register(SandboxCreateResult, SandboxCreateFormatter())
    target.register(SandboxApplyResult, SandboxApplyFormatter())
    target.register(SandboxDeleteResult, SandboxDeleteFormatter())
    target.register(SandboxDiffResult, SandboxDiffFormatter())


# Register default sandbox formatters on the central ui_dispatcher
register_sandbox_formatters()
