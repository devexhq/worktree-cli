"""Shared formatting helpers for workspace initialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.text import Text

from worktree.common.utils import display_path
from worktree.core.bootstrap import BootstrapResult, WorkspaceInitResult
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
    if result.repaired:
        renderables.append(
            Text.from_markup(f"[bold green]✔  Worktree structure repaired at {worktree_label}[/bold green]")
        )
        renderables.extend(render_path_bullets(result.dirs_created, "Created missing", cwd))
    elif result.root_created or result.dirs_created:
        renderables.append(Text.from_markup(f"[bold green]✔  Initialized Worktree at {worktree_label}[/bold green]"))
        renderables.extend(render_path_bullets(result.dirs_created, "Created", cwd))
    else:
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
    lines = "\n".join(data.errors)
    if data.fixes:
        lines += "\nFix:\n" + "\n".join(f"  {fix}" for fix in data.fixes)
    return Panel.fit(f"[bold red]Initialization Failed![/bold red]\n{lines}", border_style="red")


def render_bootstrap_failure(data: WorkspaceInitResult) -> Panel:
    """Render panel when bootstrap step fails."""
    assert data.bootstrap_result is not None
    lines = "\n".join(f"  {err}" for err in data.bootstrap_result.errors)
    fixes = data.bootstrap_result.fixes or [
        "Resolve the path conflict above, then rerun [bold cyan]wt init[/bold cyan]."
    ]
    remediation = "\nFix:\n" + "\n".join(f"  {fix}" for fix in fixes)
    return Panel.fit(f"[bold red]Failed to initialize Worktree:[/bold red]\n{lines}{remediation}", border_style="red")


def render_config_failure(data: WorkspaceInitResult) -> Panel:
    """Render panel when configuration generation fails."""
    assert data.config_result is not None
    lines = "\n".join(f"- {err}" for err in data.config_result.errors)
    if data.config_result.fixes:
        lines += "\nFix:\n" + "\n".join(f"  {fix}" for fix in data.config_result.fixes)
    return Panel.fit(f"[bold red]Failed to generate config:[/bold red]\n{lines}", border_style="red")


def render_failure_panel(data: WorkspaceInitResult) -> Panel | None:
    """Render failure panels for preflight, bootstrap, or configuration generation errors."""
    if data.bootstrap_result is None and data.errors:
        return render_preflight_failure(data)
    if data.bootstrap_result is not None and not data.bootstrap_result.ok:
        return render_bootstrap_failure(data)
    if data.config_result is not None and not data.config_result.ok:
        return render_config_failure(data)
    return None
