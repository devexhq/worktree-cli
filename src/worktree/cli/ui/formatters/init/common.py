"""Shared formatting helpers for workspace initialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.formatters.common import (
    ERROR_PANEL_STYLE,
    render_list_errors,
    render_list_fixes,
)
from worktree.common.utils import display_path
from worktree.core.bootstrap import (
    BootstrapOutcome,
    BootstrapResult,
    InitFailureMode,
    WorkspaceInitResult,
)
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


def render_path_bullets(paths: list[Path], label: str, cwd: Path) -> list[Any]:
    """Render bullet list of paths relative to cwd."""
    lines: list[Any] = [Text.from_markup(f"[bold dim]{label}:[/bold dim]")]
    for path in paths:
        lines.append(Text.from_markup(f"  [dim]•[/dim] [cyan]{display_path(path, cwd)}[/cyan]"))
    return lines


def render_bootstrap_lines(result: BootstrapResult, cwd: Path) -> list[Any]:
    """Render bootstrap result status and created directory lines."""
    renderables: list[Any] = []
    worktree_label = display_path(cwd / ".worktree", cwd)
    if result.outcome == BootstrapOutcome.REPAIRED:
        renderables.append(
            Text.from_markup(f"[bold green]✔  Worktree structure repaired at {worktree_label}[/bold green]")
        )
        renderables.extend(render_path_bullets(result.dirs_created, "Created missing", cwd))
    elif result.outcome == BootstrapOutcome.INITIALIZED:
        renderables.append(Text.from_markup(f"[bold green]✔  Initialized Worktree at {worktree_label}[/bold green]"))
        renderables.extend(render_path_bullets(result.dirs_created, "Created", cwd))
    elif result.outcome == BootstrapOutcome.ALREADY_INITIALIZED:
        renderables.append(
            Text.from_markup(f"[bold green]✔  Worktree already initialized at {worktree_label}[/bold green]")
        )
        renderables.append(Text.from_markup("[bold dim]No changes required.[/bold dim]"))
    return renderables


def render_config_lines(result: ConfigGenerationResult, cwd: Path) -> list[Any]:
    """Render config generation result lines."""
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


def render_seed_lines(result: SeedResult, cwd: Path) -> list[Any]:
    """Render template seed result lines."""
    renderables: list[Any] = [Text("")]
    if result.created_files:
        renderables.append(Text.from_markup("[bold green]✔  Seeded starter workflows[/bold green]"))
        renderables.extend(render_path_bullets(result.created_files, "Created", cwd))
    elif result.overwritten_files:
        renderables.append(Text.from_markup("[bold green]✔  Refreshed starter workflows[/bold green]"))
    else:
        renderables.append(Text.from_markup("[bold green]✔  Starter workflows already present[/bold green]"))

    if result.skipped_existing_files:
        renderables.extend(render_path_bullets(result.skipped_existing_files, "Skipped existing", cwd))

    if result.errors:
        lines = "\n".join(f"- {err}" for err in result.errors)
        renderables.append(
            Panel.fit(
                f"[bold red]Starter workflow seeding failed:[/bold red]\n{lines}",
                border_style="red",
            )
        )
    return renderables


def render_preflight_failure(data: WorkspaceInitResult) -> Panel:
    """Render panel when initialization preflight checks fail."""
    lines = render_list_errors(data.errors, separator="\n")
    if fixes_msg := render_list_fixes(data.fixes, bullet="  "):
        lines = f"{lines}\n{fixes_msg}"
    return Panel.fit(f"[bold red]Initialization Failed![/bold red]\n{lines}", border_style=ERROR_PANEL_STYLE)


def render_bootstrap_failure(data: WorkspaceInitResult) -> Panel:
    """Render panel when bootstrap step fails."""
    assert data.bootstrap_result is not None
    lines = "\n".join(f"  {err}" for err in data.bootstrap_result.errors)
    fixes = data.bootstrap_result.fixes or [
        "Resolve the path conflict above, then rerun [bold cyan]wt init[/bold cyan]."
    ]
    remediation = render_list_fixes(fixes, bullet="  ")
    return Panel.fit(
        f"[bold red]Failed to initialize Worktree:[/bold red]\n{lines}\n{remediation}",
        border_style=ERROR_PANEL_STYLE,
    )


def render_config_failure(data: WorkspaceInitResult) -> Panel:
    """Render panel when configuration generation fails."""
    assert data.config_result is not None
    lines = "\n".join(f"- {err}" for err in data.config_result.errors)
    if fixes_msg := render_list_fixes(data.config_result.fixes, bullet="  "):
        lines = f"{lines}\n{fixes_msg}"
    return Panel.fit(f"[bold red]Failed to generate config:[/bold red]\n{lines}", border_style=ERROR_PANEL_STYLE)


def render_failure_panel(data: WorkspaceInitResult) -> Panel | None:
    """Render failure panels for preflight, bootstrap, or configuration generation errors."""
    if data.failure_mode == InitFailureMode.PREFLIGHT:
        return render_preflight_failure(data)
    if data.failure_mode == InitFailureMode.BOOTSTRAP:
        return render_bootstrap_failure(data)
    if data.failure_mode == InitFailureMode.CONFIG_GENERATION:
        return render_config_failure(data)
    return None
