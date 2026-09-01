"""ComponentFormatters for init CLI domain objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.common.utils import display_path
from worktree.core.bootstrap import (
    BootstrapResult,
    WorkspaceInitResult,
)
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


def _render_path_bullets(paths: list[Path], label: str, cwd: Path) -> list[Any]:
    lines: list[Any] = [Text.from_markup(f"[bold dim]{label}:[/bold dim]")]
    for path in paths:
        lines.append(Text.from_markup(f"  [dim]•[/dim] [cyan]{display_path(path, cwd)}[/cyan]"))
    return lines


def _render_bootstrap_lines(result: BootstrapResult, cwd: Path) -> list[Any]:
    renderables: list[Any] = []
    worktree_label = display_path(cwd / ".worktree", cwd)
    if result.repaired:
        renderables.append(
            Text.from_markup(f"[bold green]✔  Worktree structure repaired at {worktree_label}[/bold green]")
        )
        renderables.extend(_render_path_bullets(result.dirs_created, "Created missing", cwd))
    elif result.root_created or result.dirs_created:
        renderables.append(Text.from_markup(f"[bold green]✔  Initialized Worktree at {worktree_label}[/bold green]"))
        renderables.extend(_render_path_bullets(result.dirs_created, "Created", cwd))
    else:
        renderables.append(
            Text.from_markup(f"[bold green]✔  Worktree already initialized at {worktree_label}[/bold green]")
        )
        renderables.append(Text.from_markup("[bold dim]No changes required.[/bold dim]"))
    return renderables


def _render_config_lines(result: ConfigGenerationResult, cwd: Path) -> list[Any]:
    if not result.config_path:
        return []
    renderables: list[Any] = [Text("")]
    label = f"./{display_path(result.config_path, cwd)}"
    if result.created:
        renderables.append(Text.from_markup(f"  [dim]•[/dim] Generated config: [cyan]{label}[/cyan]"))
    elif result.overwritten:
        renderables.append(Text.from_markup(f"  [dim]•[/dim] Regenerated config: [cyan]{label}[/cyan]"))
    elif result.repaired:
        renderables.append(Text.from_markup(f"  [dim]•[/dim] Repaired config: [cyan]{label}[/cyan]"))
        if result.inserted_keys:
            renderables.append(Text.from_markup("[bold dim]  Added missing keys:[/bold dim]"))
            for key in result.inserted_keys:
                renderables.append(Text.from_markup(f"  [dim]•[/dim] [cyan]{key}[/cyan]"))
    elif result.skipped_existing:
        renderables.append(Text.from_markup(f"  [dim]•[/dim] Config exists: [cyan]{label}[/cyan]"))
    return renderables


def _render_seed_lines(result: SeedResult, cwd: Path) -> list[Any]:
    renderables: list[Any] = [Text("")]
    if result.created_files:
        renderables.append(Text.from_markup("[bold green]✔  Seeded starter workflows[/bold green]"))
        renderables.extend(_render_path_bullets(result.created_files, "Created", cwd))
    elif result.overwritten_files:
        renderables.append(Text.from_markup("[bold green]✔  Refreshed starter workflows[/bold green]"))
    else:
        renderables.append(Text.from_markup("[bold green]✔  Starter workflows already present[/bold green]"))

    if result.skipped_existing_files:
        renderables.extend(_render_path_bullets(result.skipped_existing_files, "Skipped existing", cwd))

    if result.errors:
        lines = "\n".join(f"- {err}" for err in result.errors)
        renderables.append(
            Panel.fit(
                f"[bold red]Starter workflow seeding failed:[/bold red]\n{lines}",
                border_style="red",
            )
        )
    return renderables


def _render_failure_panel(data: WorkspaceInitResult) -> Panel | None:
    if data.bootstrap_result is None and data.errors:
        lines = "\n".join(data.errors)
        return Panel.fit(f"[bold red]Initialization Failed![/bold red]\n{lines}", border_style="red")
    if data.bootstrap_result is not None and not data.bootstrap_result.ok:
        lines = "\n".join(f"  {err}" for err in data.bootstrap_result.errors)
        remediation = "\nFix:\n  resolve the path conflict above, then rerun [bold cyan]wt init[/bold cyan]."
        return Panel.fit(
            f"[bold red]Failed to initialize Worktree:[/bold red]\n{lines}{remediation}", border_style="red"
        )
    if data.config_result is not None and not data.config_result.ok:
        lines = "\n".join(f"- {err}" for err in data.config_result.errors)
        return Panel.fit(f"[bold red]Failed to generate config:[/bold red]\n{lines}", border_style="red")
    return None


class WorkspaceInitFormatter(ComponentFormatter[WorkspaceInitResult]):
    """Formatter for workspace initialization results."""

    def to_rich(self, data: WorkspaceInitResult) -> Any:
        """Render initialization summary, repair details, or failure panels.

        Args:
            data: Structured workspace initialization result.

        Returns:
            Rich renderable object (Group or Panel).
        """
        failure_panel = _render_failure_panel(data)
        if failure_panel is not None:
            return failure_panel

        cwd = (
            data.bootstrap_result.root_path.parent
            if data.bootstrap_result is not None and data.bootstrap_result.root_path
            else Path.cwd()
        )

        renderables: list[Any] = [Text("")]
        if data.bootstrap_result is not None:
            renderables.extend(_render_bootstrap_lines(data.bootstrap_result, cwd))
        if data.config_result is not None:
            renderables.extend(_render_config_lines(data.config_result, cwd))
        if data.seed_result is not None:
            renderables.extend(_render_seed_lines(data.seed_result, cwd))
        renderables.append(Text(""))
        renderables.append(
            Text.from_markup(
                "[bold dim]Next: run [bold cyan]wt config show[/bold cyan] or [bold cyan]wt workflow list[/bold cyan][/bold dim]"
            )
        )
        return Group(*renderables)

    def to_json_serializable(self, data: WorkspaceInitResult) -> dict[str, Any]:
        """Convert WorkspaceInitResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured workspace initialization result.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


InitOutcomeFormatter = WorkspaceInitFormatter


def register_init_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register all init ComponentFormatter instances on a UiDispatcher.

    Args:
        dispatcher: UiDispatcher instance to register on. Defaults to ui_dispatcher.
    """
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(WorkspaceInitResult, WorkspaceInitFormatter())


# Register default init formatters on the central ui_dispatcher
register_init_formatters()
